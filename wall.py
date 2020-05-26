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


import can,isotp,u3,helpers2,sys

from pathlib import Path

sys.path.append(str(Path.home())+"/Desktop/TWCManager/")
import TWCManager



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

SWCANname='can10'						#name of the interface for the single wire can bus, the charge port can bus.





LNDhost="127.0.0.1:10009"
LNDnetwork='mainnet'						#'mainnet' or 'testnet'

LabJackSerialNumber=222222222					#need to do this if have multiple LabJacks plugged into the same computer
ProximityVoltage=1.5						#Voltage that indicates charge cable has been plugged in


CurrentRate=1							#sat/(W*hour)
WhoursPerPayment=int(25)					#W*hour/payment
RequiredPaymentAmount=int(WhoursPerPayment*CurrentRate)		#sat/payment
MaxAmps=24



RelayON=True							#True for High ON logic, False for Low ON logic. (wall unit uses HIGH ON logic and car unit uses LOW ON logic for now)

################################################################





################################################################
#initialize variables
################################################################


Proximity=False
OfferAccepted=False
ReInsertedMessagePrinted=False
ProximityCheckStartTime=-1
ProximityLostTime=0



Volts=None
Amps= None

TimeLastOfferSent=time()

ChargeStartTime=-1

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


################################################################



################################################################
#initialize CAN ISOTP
################################################################

#CAN ISOTP is a higher level protocol used to transfer larger amounts of data than the base CAN allows
#this creates its own separate socket to the CAN bus on the same single wire can interface from the
#other standard can messaging that occurs in this script

SWCAN_ISOTP = isotp.socket()				#default recv timeout is 0.1 seconds
#SWCAN_ISOTP.set_fc_opts(stmin=5, bs=10)		#see https://can-isotp.readthedocs.io/en/latest/isotp/socket.html#socket.set_fc_opts
SWCAN_ISOTP.set_fc_opts(stmin=25, bs=10)
SWCAN_ISOTP.bind(SWCANname, isotp.Address(rxid=1996, txid=1997))		#note: rxid of wall is txid of car, and txid of wall is rxid of the car



################################################################
























################################################################

GUI.start()			#starts .run() (and maybe some other stuff?)

################################################################




TWCManager.MainThread.start()
while len(TWCManager.master.slaveTWCRoundRobin)<1:			#wait until connected to a wall unit.
	sleep(.1)
WallUnit=TWCManager.master.slaveTWCRoundRobin[0]			#only one wall unit now, so using number 0 blindly



####################
#not positive these are needed here since will be done below with every instance of the loop, but do it anyway because want something defined before sendStartCommand
TWCManager.master.setChargeNowAmps(MaxAmps)				#set maximum current. need to refine this statement if have multiple wall units.
TWCManager.master.setChargeNowTimeEnd(int(3600))			#set how long to hold the current for, in seconds. need to refine this statement if have multiple wall units.
####################

TWCManager.master.sendStartCommand()					#need to refine this statement if have multiple wall units.
TWCManager.master.settings['chargeStopMode']=3
TWCManager.master.saveSettings()

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


		#not sure how to make ChargeNow perpetual, so just add an hour on every loop.
		TWCManager.master.setChargeNowTimeEnd(int(3600))		#set how long to hold the current for, in seconds. need to refine this statement if have multiple wall units.


		ain0bits, = LabJack.getFeedback(u3.AIN(0))	#channel 0, also note, the "," after "ain0bits" which is used to unpack the list returned by getFeedback()
		TheOutputVoltage=LabJack.binaryToCalibratedAnalogVoltage(ain0bits,isLowVoltage=False,channelNumber=0)

		#print TheOutputVoltage

		if (TheOutputVoltage > ProximityVoltage-0.05) and (not Proximity):

			if (time()>ProximityLostTime+15):			#wait at least 15 seconds after the plug was removed to start looking for proximity again
				if ProximityCheckStartTime==-1:
					ProximityCheckStartTime=time()
					TimeStampedPrint("plug inserted")	#or was already inserted, but finished waiting 15 seconds
					BigStatus='Charge Cable Inserted'
					SmallStatus=''
				elif time()>ProximityCheckStartTime+3:		#proximity must be maintained for at least 3 seconds
					Proximity=True
					ReInsertedMessagePrinted=False
					ProximityCheckStartTime=-1

					LabJack.getFeedback(u3.BitStateWrite(4, RelayON))	# Set FIO4 to output ON
					TimeStampedPrint("relay energized")
					CurrentTime=time()
					InitialInvoice=True
					EnergyDelivered=0
					EnergyPaidFor=0


			elif not ReInsertedMessagePrinted:
				TimeStampedPrint("plug re-inserted in less than 15 seconds, waiting")
#need to add this waiting logic to the car unit as well, so that both wall and car unit are in sync and start measuring energy delivery at the same time.

				BigStatus='Waiting'
				SmallStatus=''

				ReInsertedMessagePrinted=True


			print(str(TheOutputVoltage))



		elif (TheOutputVoltage < ProximityVoltage-0.05*2) and (not Proximity) and (ProximityCheckStartTime!=-1 or ReInsertedMessagePrinted):
			ProximityLostTime=time()
			ReInsertedMessagePrinted=False
			ProximityCheckStartTime=-1
			TimeStampedPrint("plug was removed before the relay was energized")
			print(str(TheOutputVoltage))

			BigStatus='Charge Cable Removed'
			SmallStatus=''
			sleep(2)
			BigStatus='Insert Charge Cable Into Car'
			SmallStatus='Waiting For Charge Cable To Be Inserted'


		elif (TheOutputVoltage < ProximityVoltage-0.05*2) and (Proximity):
			Proximity=False
			ProximityLostTime=time()
			TimeStampedPrint("plug removed\n\n\n")
			print(str(TheOutputVoltage))

			BigStatus='Charge Cable Removed'
			SmallStatus=''
			sleep(2)
			BigStatus='Insert Charge Cable Into Car'
			SmallStatus='Waiting For Charge Cable To Be Inserted'

			#reset the values of current and voltage....actually, may not be needed here anymore ? need to remove and test.
			Volts	=	None
			Amps	=	None

			LabJack.getFeedback(u3.BitStateWrite(4, RelayOFF))	# Set FIO4 to output OFF



		Volts=WallUnit.voltsPhaseA
		Amps=WallUnit.reportedAmpsActual




		if Proximity:

			message = SWCAN.recv(timeout=.075)

			if PowerKilled:
				BigStatus='Stopped Charging'
				ChargeStartTime=-1		#makes stop counting charge time even through there is still proximity

			else:

				if (Volts is not None) and (Amps is not None):		#should probably wait above when WallUnit object is created until these are available.
					PreviousTime=CurrentTime
					CurrentTime=time()
					deltaT=(CurrentTime-PreviousTime)/3600		#hours, small error on first loop when SWCANActive is initially True

					EnergyDelivered+=deltaT*Volts*Amps		#W*hours


				if OfferAccepted:

						if PendingInvoice:

							#check to see if the current invoice has been paid

							OutstandingInvoiceStatus=lnd.lookup_invoice(OutstandingInvoice.r_hash)
							if OutstandingInvoiceStatus.settled:
								EnergyPaidFor+=OutstandingInvoiceStatus.value/(CurrentRate)		#W*hours
								PendingInvoice=False
								InitialInvoice=False							#reset every time just to make the logic simpler

								TimeStampedPrint('WhoursDelivered: '+RoundAndPadToString(EnergyDelivered,1)+',   Volts: '+RoundAndPadToString(Volts,2)+',   Amps: '+RoundAndPadToString(Amps,2))
								TimeStampedPrint("payment received, time since last payment received="+str(time()-LastPaymentReceivedTime)+"s")

								LastPaymentReceivedTime=time()

								SmallStatus='Payment Received'


						#now that the pending invoices have been processed, see if it's time to send another invoice, or shutdown power if invoices haven't been paid in a timely manner.

						#time to send another invoice
						#adjust multiplier to decide when to send next invoice. can really send as early as possible because car just waits until it's really time to make a payment.
						#was 0.5, but higher is probably really better because don't know how long the lightning network payment routing is actually going to take.
						#send payment request after 10% has been delivered (90% ahead of time)
						#note, because below 1% error is allowed, this test may actually not have much meaning considering over the course of a charging cycle
						#the total error may be larger than an individual payment amount, so EnergyPaidFor-EnergyDelivered is likely less than 0 and therefor
						#a new invoice will just be sent right after the previous invoice was paid, rather than waiting.
						if ((EnergyPaidFor-EnergyDelivered)<RequiredPaymentAmount*0.90) and not PendingInvoice:
							RequiredPaymentAmount=WhoursPerPayment*CurrentRate				#sat

							OutstandingInvoice=lnd.add_invoice(RequiredPaymentAmount)

#need to do a try except here, because the buyer may not be listening properly
							SWCAN_ISOTP.send(OutstandingInvoice.payment_request.encode())			#send the new invoice using CAN ISOTP
							TimeStampedPrint("sent new invoice for "+str(RequiredPaymentAmount)+" satoshis")
							SmallStatus='Payment Requested'

							PendingInvoice=True

						elif PendingInvoice:									#waiting for payment
							#TimeStampedPrint("waiting for payment, and limit not yet reached")
							pass

						else:
							#TimeStampedPrint("waiting to send next invoice")
							pass



				else:
					#try to negotiate the offer
					if (message is not None) and (message.arbitration_id == 1999 and message.data[0]==1):		#don't really need to convert to int since hex works fine for a 0 vs 1
						#buyer accepted the rate
						OfferAccepted=True
						TimeStampedPrint("buyer accepted rate")

						ChargeStartTime=datetime.now()

						BigStatus='Charging'
						SmallStatus='Sale Terms Accepted'

						FirstRequiredPaymentAmount=1*RequiredPaymentAmount				#sat, adjust multiplier if desire the first payment to be higher than regular payments.

						OutstandingInvoice=lnd.add_invoice(FirstRequiredPaymentAmount)
						SWCAN_ISOTP.send(OutstandingInvoice.payment_request.encode())
						TimeStampedPrint("sent first invoice for "+str(FirstRequiredPaymentAmount)+" satoshis")

						LastPaymentReceivedTime=time()			#fudged since no payment actually received yet, but want to still time since invoice sent, and need variable to be initialized.

						PendingInvoice=True

					elif (message is not None) and (message.arbitration_id == 1999 and message.data[0]==0):
						OfferAccepted=False
						TimeStampedPrint("buyer rejected rate")
						#SmallStatus='Sale Terms Rejected'

					elif (TimeLastOfferSent+1)<time():			#only send once per second and give the outer loop a chance to process all incoming messages, otherwise will send multiple offers in between the tesla messages and the car module messages.
						#provide the offer

#need to do a try except here, because the buyer may not be listening properly
						SWCAN.send(Message(arbitration_id=1998,data=int(WhoursPerPayment).to_bytes(4, byteorder='little')+int(RequiredPaymentAmount).to_bytes(4, byteorder='little'),is_extended_id=False))
						TimeLastOfferSent=time()
						TimeStampedPrint("provided an offer of "+RoundAndPadToString(WhoursPerPayment,1)+" W*hour for a payment of "+str(RequiredPaymentAmount)+" satoshis ["+RoundAndPadToString(CurrentRate,1)+" satoshis/(W*hour)]")
						SmallStatus='Provided An Offer'
						#SmallStatus='Sale Terms Offered To Vehicle'



				if (
						#buyer must pay ahead 20% for all payments but the first payment (must pay after 80% has been delivered).
						#also allow 1% error due to measurement error as well as transmission losses between the car and the wall unit.
						#this error basically needs to be taken into consideration when setting the sale rate.
						(((EnergyPaidFor-EnergyDelivered*0.99)<WhoursPerPayment*0.20)	and not	InitialInvoice)

							or

						#buyer can go into debt 30% before the first payment, also allowing for 1% error as above, although that may be really needed for the first payment.
						(((EnergyPaidFor-EnergyDelivered*0.99)<-WhoursPerPayment*0.30)	and	InitialInvoice)
					):

					TimeStampedPrint("buyer never paid, need to kill power")
					PowerKilled=True
					TWCManager.master.sendStopCommand()					#need to refine this statement if have multiple wall units.
					SmallStatus='Vehicle Did Not Make Payment'





		else:
			OfferAccepted=False
			PowerKilled=False

			sleep(.075*3)		#make this longer than the receive timeouts so that the buffers always get empty, otherwise there will be a reaction delay because the receiver is still processing old messages????



except (KeyboardInterrupt, SystemExit):

	TWCManager.MainThread.stop()
	TWCManager.MainThread.join()
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




