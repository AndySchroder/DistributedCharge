###############################################################################
###############################################################################
#Copyright (c) 2020, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################




################################################################
#import modules
################################################################

from time import sleep,time
from datetime import datetime

from lndgrpc import LNDClient
from m3 import m3, getCANvalue
from GUI import GUIThread as GUI
from collections import deque

import can,isotp,u3,helpers2,threading,sys








#want to change some values for some objects in imported modules, so couldn't use "from" when importing specific objects.
#now, assign a shorter name to the specific objects of interest that will not be changed, but will be used frequently.

Message=can.Message

RoundAndPadToString=helpers2.RoundAndPadToString
TimeStampedPrint=helpers2.TimeStampedPrint


################################################################



################################################################
#define configuration related constants
################################################################

helpers2.PrintWarningMessages=True

SWCANname='can11'						#name of the interface for the single wire can bus, the charge port can bus.
TWCANname='can12'						#name of the interface for the two wire can bus (standard can)




LNDhost="127.0.0.1:10009"
LNDnetwork='mainnet'						#'mainnet' or 'testnet'

LabJackSerialNumber=111111111					#need to do this if have multiple LabJacks plugged into the same computer



MaxRate=1.5			#sat/(W*hour)

MaxRequiredPaymentAmount=41	#sat




RelayON=False							#True for High ON logic, False for Low ON logic. (wall unit uses HIGH ON logic and car unit uses LOW ON logic for now)

################################################################





################################################################
#initialize variables
################################################################

SWCANActive=False
Proximity=False


AcceptedRate=False
TotalWhoursCharged=-1

Volts=None
Amps=None
MaxAmps=None

ChargeStartTime=-1
CurrentRate=0
RequiredPaymentAmount=0
EnergyDelivered=0
EnergyPaidFor=0

BigStatus='Insert Charge Cable Into Car'
SmallStatus='Waiting For Charge Cable To Be Inserted'

################################################################





################################################################
#initialize the LabJack U3
################################################################

try:	#don't error out if re-running the script in the same interpreter, just re-use the existing object
	LabJack=u3.U3(firstFound=False,serial=LabJackSerialNumber)	#use a specific labjack and allow multiple to be plugged in at the same time.
except:
	pass
LabJack.getCalibrationData()			#don't know what this is for.

LabJack.configIO(FIOAnalog = 15)		#is this making a permanent change and wearing out the non-volatile memory?

LabJack.getFeedback(u3.BitDirWrite(4, 1))	# Set FIO4 to digital output

RelayOFF=not RelayON				#always opposite of ON

#default power on default for output direction is high. set FIO4 to whatever the relay off logic
#requires (and actually reseting if RelayOFF==True just to keep.the logic simpler)
#may be able to combine this into one line with the above setting of the output direction?
#either way, right now, this seems to be quick enough that the coil doesn't have time to energize.
#could use the python command that sets power on defaults in another one time run script/step,
#but then that would require an setup step that modifies the device flash memory that would be better to avoid.
LabJack.getFeedback(u3.BitStateWrite(4, RelayOFF))

################################################################



################################################################
#initialize the LND RPC
################################################################

lnd = LNDClient(LNDhost, network=LNDnetwork, admin=True)

################################################################



################################################################
#initialize the CAN bus
################################################################

SWCAN = can.interface.Bus(channel=SWCANname, bustype='socketcan',can_filters=[	#only pickup IDs of interest so don't waste time processing tons of unused data
										{"can_id": 0x3d2, "can_mask": 0x7ff, "extended": False},	#battery charge/discharge
										{"can_id": 1998, "can_mask": 0x7ff, "extended": False},		#wall offer
										{"can_id": 1999, "can_mask": 0x7ff, "extended": False},		#car acceptance of offer
										{"can_id": m3.get_message_by_name('ID31CCC_chgStatus').frame_id, "can_mask": 0x7ff, "extended": False},
										{"can_id": m3.get_message_by_name('ID32CCC_logData').frame_id, "can_mask": 0x7ff, "extended": False},
										])



TWCAN = can.interface.Bus(channel=TWCANname, bustype='socketcan',can_filters=[
										{"can_id": 0x3d2, "can_mask": 0x7ff, "extended": False},	#battery charge/discharge
										{"can_id": 1990, "can_mask": 0x7ff, "extended": False},
										{"can_id": m3.get_message_by_name('ID21DCP_evseStatus').frame_id, "can_mask": 0x7ff, "extended": False},
										{"can_id": m3.get_message_by_name('ID31CCC_chgStatus').frame_id, "can_mask": 0x7ff, "extended": False},
										{"can_id": m3.get_message_by_name('ID32CCC_logData').frame_id, "can_mask": 0x7ff, "extended": False},
										])


################################################################



################################################################
#initialize CAN ISOTP
################################################################

#CAN ISOTP is a higher level protocol used to transfer larger amounts of data than the base CAN allows
#this creates its own separate socket to the CAN bus on the same single wire can interface from the
#other standard can messaging that occurs in this script

SWCAN_ISOTP = isotp.socket()			#default recv timeout is 0.1 seconds
SWCAN_ISOTP.set_fc_opts(stmin=5, bs=10)		#see https://can-isotp.readthedocs.io/en/latest/isotp/socket.html#socket.set_fc_opts
SWCAN_ISOTP.bind(SWCANname, isotp.Address(rxid=1997, txid=1996))


class ReceiveInvoices(threading.Thread):
	#this class holds the InvoiceQueue object, receives invoices, operates in another thread in daemon mode, and will shutdown if the .stop() method is used.
	#not sure if the socket should be opened and closed from within here or not. to be re-visited at a later time.
	#not sure if socket needs to be re-created every time SWCAN comes up.
	#see also:
		# https://stackoverflow.com/questions/47912701/python-how-can-i-implement-a-stoppable-thread
		# https://stackoverflow.com/questions/40382332/example-usages-of-the-stoppablethread-subclass-of-pythons-threading-thread
		# https://github.com/python/cpython/blob/2.7/Lib/threading.py#L743
		# https://stackoverflow.com/questions/27102881/python-threading-self-stop-event-object-is-not-callable

	def __init__(self,  *args, **kwargs):
		super(ReceiveInvoices, self).__init__(*args, **kwargs)
		self._stop_event = threading.Event()
		self.InvoiceQueue=deque()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

	def stop(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

	def run(self):
		while True:
			NewInvoice=SWCAN_ISOTP.recv()		#as mentioned above, SWCAN_ISOTP is set to timeout every 0.1 seconds, so it automatically sleeps for us
			if NewInvoice is not None:
				self.InvoiceQueue.append(NewInvoice)
			if self._stop_event.is_set():
				break



ReceiveInvoicesThread=ReceiveInvoices()		#create the thread
ReceiveInvoicesThread.start()			#starts .run() (and maybe some other stuff?)

################################################################






################################################################

GUI.start()			#starts .run() (and maybe some other stuff?)

################################################################




try:

	while True:

		#pass values to the GUI
		GUI.Volts=Volts
		GUI.Amps=Amps
		GUI.BigStatus=BigStatus
		GUI.SmallStatus=SmallStatus
		GUI.EnergyDelivered=EnergyDelivered
		GUI.EnergyPaidFor=EnergyPaidFor
		GUI.CurrentRate=CurrentRate
		GUI.RequiredPaymentAmount=RequiredPaymentAmount
		GUI.ChargeStartTime=ChargeStartTime
		GUI.Proximity=Proximity
		GUI.MaxAmps=MaxAmps


		if GUI._stop_event.is_set():
			sys.exit()


		messageTW = TWCAN.recv(timeout=.0075)		#don't need a long timeout here because the below timeout exists on SWCAN.
#actually, moved to after "if Proximity:", so maybe do? need to monitor CPU usage and decide.




		if (messageTW is not None) and (m3.get_message_by_name('ID21DCP_evseStatus').frame_id == messageTW.arbitration_id):
			if getCANvalue(messageTW.data,'ID21DCP_evseStatus','CP_teslaSwcanState')=="TESLA_SWCAN_ESTABLISHED":
				SWCANActive=True
			else:		#disconnect on anything else for now (may want to revisit all states and see if want to stay connected on sleep for example)
#does not seem to send another signal before going into sleep mode. need to figure out something else to do to detect, or also use voltage measured
#from labjack on pilot/proximity pin to have more confidence on what is going on, like how the wall unit operates.
#causes problems and then car errors out even though SWCAN is actually active, canbus doesn't think so, so ....
#also need to consider having a 15 second delay between pluggin/unplugging like the wall unit, so that they are both measuring energy delivery from the same start time
				SWCANActive=False
				Volts=None
				Current=None


		ain0bits, = LabJack.getFeedback(u3.AIN(0))	#channel 0, also note, the "," after "ain0bits" which is used to unpack the list returned by getFeedback()
		TheOutputVoltage=LabJack.binaryToCalibratedAnalogVoltage(ain0bits,isLowVoltage=False,channelNumber=0)

		if SWCANActive and not Proximity:
			Proximity=True
			TimeStampedPrint("plug inserted")
			BigStatus='Charge Cable Inserted'
			SmallStatus=''

			LabJack.getFeedback(u3.BitStateWrite(4, RelayON))	# Set FIO4 to output ON
			TimeStampedPrint("relay energized")

			CurrentTime=time()
			EnergyDelivered=0

		elif not SWCANActive and (Proximity):
			Proximity=False
			TimeStampedPrint("plug removed\n\n\n")

			LabJack.getFeedback(u3.BitStateWrite(4, RelayOFF))	# Set FIO4 to output OFF

			BigStatus='Charge Cable Removed'
			SmallStatus=''
			sleep(2)
			BigStatus='Insert Charge Cable Into Car'
			SmallStatus='Waiting For Charge Cable To Be Inserted'






		#can pickup on either TW or SW CAN, but better to pickup on TW can because the wall unit can't inject bogus data onto that bus
		#also, if picking up on SW CAN, need to do it after the "if Proximity:" statement below.

		if (messageTW is not None) and (messageTW.arbitration_id == 0x3d2):				#0x syntax seems to automatically convert to an integer.
			#Model3CAN.dbc seems to have this mixed up with kWhoursDischarged? can fix Model3CAN.dbc, but just keeping it this way as an excersise on how decoding actually works.
			TotalWhoursCharged=int.from_bytes(messageTW.data[0:4],byteorder='little')		#seems to include regen?
			TotalWhoursDischarged=int.from_bytes(messageTW.data[4:8],byteorder='little')		#not needed, but just keeping in here so understand what the rest of the message contains

		elif (messageTW is not None) and (m3.get_message_by_name('ID31CCC_chgStatus').frame_id == messageTW.arbitration_id):
			Volts=getCANvalue(messageTW.data,'ID31CCC_chgStatus','CC_line1Voltage')
			MaxAmps=getCANvalue(messageTW.data,'ID31CCC_chgStatus','CC_currentLimit')

		elif (messageTW is not None) and (m3.get_message_by_name('ID32CCC_logData').frame_id == messageTW.arbitration_id):
			if getCANvalue(messageTW.data,'ID32CCC_logData','CC_logIndex') == 'Mux1':		#Signals available in the message seem to be dependent on this value.
				Amps=getCANvalue(messageTW.data,'ID32CCC_logData','CC_conn1Current')
		#END can pickup on either TW or SW CAN, but better to pickup on TW can because the wall unit can't inject bogus data onto that bus







		if Proximity:


			# according to https://github.com/hardbyte/python-can/issues/768 there is some kind of buffer. not sure what it actually is
			# but since the frequency of all messages of interest is low after applying the filter, hoping it is good enough for now.
			#timeout is used instead of a sleep in this loop too
			#do this here instead of above with TWCAN in order to slightly reduce delay after Proximity initially becomes True and data will be present on the SWCAN.
			message = SWCAN.recv(timeout=.0075)
#maybe too short of a timeout? was having problems with delayed messages and maybe there were too many messages and they were not being processed quickly enough, so lowered it by 10X to 0.0075.
#need to do more testing and also measure CPU usage.


			if AcceptedRate and TotalWhoursCharged !=-1:

				#not yet used. need to add to the GUI or some other kind of report. can help understand how much energy is wasted warming the battery up as well as charger
				#efficinecy since the Tesla GUI is very misleading on how much energy you are actually using
				EnergyAddedToBattery=TotalWhoursCharged-TotalWhoursCharged_start

				if (Volts is not None) and (Amps is not None):		#can't start doing anything until an initial voltage and current reading is obtained on the can bus because need that to decide when to pay.

					PreviousTime=CurrentTime
					CurrentTime=time()
					deltaT=(CurrentTime-PreviousTime)/3600		#hours, small error on first loop when Proximity is initially True

					EnergyDelivered+=deltaT*Volts*Amps		#W*hours


					if len(ReceiveInvoicesThread.InvoiceQueue)>0:		#invoices are waiting to be paid
						oldestInvoice=ReceiveInvoicesThread.InvoiceQueue.popleft()
						AmountRequested=lnd.decode_payment_request(oldestInvoice).num_satoshis

#						TimeStampedPrint("seller wants to be paid "+str(AmountRequested)+" satoshis")
						SmallStatus='Payment Requested'

						if (
								((EnergyPaidFor-EnergyDelivered)<WhoursPerPayment*0.70)			#not asking for payment before energy is delivered (allowed to pay after 30% has been delivered (70% ahead of time)
									and
								(
									(AmountRequested<=RequiredPaymentAmount)			#not asking for too much payment
										or
									(
										(AmountRequested<=2*RequiredPaymentAmount)
											and
										(EnergyPaidFor==0)					#first payment allows 2x normal payment amount.
									)
								)
							):										#if all good, then it's time to send another invoice

							try:

								TimeStampedPrint("sending payment")
#should check to make sure the "expiry" has not passed on the invoice yet before paying????
								lnd.send_payment(oldestInvoice)			#seems to block code execution until the payment is routed, or fails

								EnergyPaidFor+=AmountRequested/CurrentRate

								TimeStampedPrint('WhoursReceived: '+RoundAndPadToString(EnergyDelivered,1)+',   Volts: '+RoundAndPadToString(Volts,2)+',   Amps: '+RoundAndPadToString(Amps,2))

								TimeStampedPrint("sent payment for "+str(AmountRequested)+" satoshis")

								SmallStatus='Payment Sent'

							except:
#lnd.send_payment doesn't fail (raise a python exception) if the payment fails to route, only if lnd.send_payment can't contact the lnd node. so, need to check the response from lnd.send_payment to see what actually happened
								raise

						else:
							#seller is asking for payment to quickly, waiting until they deliver energy that was agreed upon.
							#if they aren't happy and think they delivered enough, they will shut down.
							#currently, the buyer will tolerate up to 20% of error. the seller tolerates 30%
							#because they need to give time for a payment to actually be made.
							#need to do something if AmountRequested>RequiredPaymentAmount and EnergyPaidFor>0


							ReceiveInvoicesThread.InvoiceQueue.appendleft(oldestInvoice)		#put the invoice back in the queue
#							TimeStampedPrint("not yet time to pay, waiting")
					else:
#						TimeStampedPrint("waiting for next invoice")
						pass



			elif (message is not None) and (message.arbitration_id == 1998) and TotalWhoursCharged !=-1:	#offer received
				WhoursPerPayment=int.from_bytes(message.data[0:4],byteorder='little')			#Whours_offered
				RequiredPaymentAmount=int.from_bytes(message.data[4:8],byteorder='little')		#for_sat
				CurrentRate=RequiredPaymentAmount/WhoursPerPayment					#1/(Whours_offered/for_sat)

				if (CurrentRate<MaxRate) and (RequiredPaymentAmount<MaxRequiredPaymentAmount):		#accept the rate, until SWCAN goes down. probably need to upgrade to allow rate changes during a charging session, but for now, this is how it works.
					ReceiveInvoicesThread.InvoiceQueue.clear()		#all previous invoices are no longer be valid as far as the buyer is concerned, so ignore them
					EnergyDelivered=0
					EnergyPaidFor=0
					AcceptedRate=True
					TotalWhoursCharged_start=TotalWhoursCharged

					#print('getting ready to accept an offer')

					SWCAN.send(Message(arbitration_id=1999,data=[True],is_extended_id=False))
					TimeStampedPrint("accepted an offer of "+RoundAndPadToString(WhoursPerPayment,1)+" W*hour for a payment of "+str(RequiredPaymentAmount)+" satoshis ["+RoundAndPadToString(CurrentRate,1)+" satoshis/(W*hour)]")

					ChargeStartTime=datetime.now()

					BigStatus='Charging'
					SmallStatus='Accepted Sale Terms'


				else:					#don't accept the rate, it's too high. wait and see if a lower offer is made.
					SWCAN.send(Message(arbitration_id=1999,data=[False],is_extended_id=False))
					TimeStampedPrint("rate or payment amount too high, not accepting")
					SmallStatus='Rejected Sale Terms, Waiting for a Better Offer'
#provide more detail in outputs on why was not accepted



			else:
				#continue to wait for an offer or TotalWhoursCharged
				pass

		else:
			AcceptedRate=False





except (KeyboardInterrupt, SystemExit):

	ReceiveInvoicesThread.stop()
	ReceiveInvoicesThread.join()
	GUI.stop()
	GUI.join()	#for some reason if this is not used, python tries too quit before the stop command is received by the thread and it gracefully shutdown and then it takes longer for tk to timeout and close the interpreter?

	TimeStampedPrint("quitting")

except:
	raise

finally:

	# the labjack remembers the state last set after the script terminates, until the USB cable is removed,
	# so Set FIO4 to output OFF so the relay denergizes
	LabJack.getFeedback(u3.BitStateWrite(4, RelayOFF))

	TimeStampedPrint("turned off relay\n\n\n")




