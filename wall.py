#!/usr/bin/env python3


###############################################################################
###############################################################################
#Copyright (c) 2022, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################




################################################################
#import modules
################################################################

from time import sleep,time
from datetime import datetime,timedelta

from lndgrpc import LNDClient
from m3 import m3, getCANvalue
from GUI import GUIThread as GUI
from gpiozero import LED


import can,isotp,helpers2,sys,mcp3008

from pathlib import Path

sys.path.append(str(Path.home())+"/Desktop/TWCManager/")
import TWCManager



#want to change some values for some objects in imported modules, so couldn't use "from" when importing specific objects.
#now, assign a shorter name to the specific objects of interest that will not be changed, but will be used frequently.

Message=can.Message

FormatTimeDeltaToPaddedString=helpers2.FormatTimeDeltaToPaddedString
RoundAndPadToString=helpers2.RoundAndPadToString
TimeStampedPrint=helpers2.TimeStampedPrint


################################################################


################################################################
#define configuration related constants
################################################################

helpers2.PrintWarningMessages=True

print('')
print('')
TimeStampedPrint('startup!')

SWCANname='can0'						#name of the interface for the single wire can bus, the charge port can bus.





LNDhost="127.0.0.1:10009"
LNDnetwork='mainnet'						#'mainnet' or 'testnet'

ProximityVoltage=1.5						#Voltage that indicates charge cable has been plugged in
ProximityVoltageTolerance=0.05*2


CurrentRate=1							#sat/(W*hour)
WhoursPerPayment=int(25)					#W*hour/payment
RequiredPaymentAmount=int(WhoursPerPayment*CurrentRate)		#sat/payment
MaxAmps=6       #5 doesn't seem to work (the car just reverts to 6 but the Distributed Charge display still says 5), but if 6 is used, can manually drop to 5 on the car screen. don't want to go between 7 and 18 amps because it tries to do the "spike amps", and this also includes manually overriding on the car screen.




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
#initialize the mcp3008
################################################################

Vref=3.3
adc = mcp3008.MCP3008(1,max_speed_hz=int(976000/15))

def PilotAnalogVoltage():
	return adc.read([mcp3008.CH1],Vref)[0]*7.6-12-.22

def ProximityAnalogVoltage():
	return adc.read([mcp3008.CH0],Vref)[0]*3.2/2.2



################################################################




################################################################
#initialize GPIO
################################################################

SWCAN_Relay = LED(16)

#should be off on boot, but just make sure it is off on startup in case the script crashed/killed with it on and is being restarted without rebooting.
SWCAN_Relay.off()


################################################################



################################################################
#initialize the LND RPC
################################################################

lnd = LNDClient(LNDhost, network=LNDnetwork, macaroon_filepath=str(Path.home())+'/.lnd/data/chain/bitcoin/mainnet/invoice.macaroon')

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
SWCAN_ISOTP.set_fc_opts(stmin=25, bs=10)		#see https://can-isotp.readthedocs.io/en/latest/isotp/socket.html#socket.set_fc_opts
SWCAN_ISOTP.bind(SWCANname, isotp.Address(rxid=1996, txid=1997))		#note: rxid of wall is txid of car, and txid of wall is rxid of the car



################################################################
























################################################################

GUI.start()			#starts .run() (and maybe some other stuff?)

################################################################




TWCManager.MainThread.start()
while len(TWCManager.master.slaveTWCRoundRobin)<1:			#wait until connected to a wall unit.
	#this is not deterministic though because seems to disconnect sometimes, especially when using crontab to lauch the scrpt on boot (which is really weird).
	sleep(.1)

myTWCID=TWCManager.master.slaveTWCRoundRobin[0].TWCID			#only one wall unit now, so using number 0 blindly
TimeStampedPrint('TWCID: '+str(myTWCID))

TimeStampedPrint("should be connected to the TWC")


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


		TheOutputVoltage=ProximityAnalogVoltage()

		#print TheOutputVoltage

		if (TheOutputVoltage > ProximityVoltage-ProximityVoltageTolerance) and (not Proximity):

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

					SWCAN_Relay.on()
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


			TimeStampedPrint('Proximity Voltage: '+str(TheOutputVoltage))



		elif (TheOutputVoltage < ProximityVoltage-ProximityVoltageTolerance*2) and (not Proximity) and (ProximityCheckStartTime!=-1 or ReInsertedMessagePrinted):
			ProximityLostTime=time()
			ReInsertedMessagePrinted=False
			ProximityCheckStartTime=-1
			TimeStampedPrint("plug was removed before the relay was energized")
			TimeStampedPrint('Proximity Voltage: '+str(TheOutputVoltage))

			BigStatus='Charge Cable Removed'
			SmallStatus=''
			sleep(2)
			BigStatus='Insert Charge Cable Into Car'
			SmallStatus='Waiting For Charge Cable To Be Inserted'


		elif (TheOutputVoltage < ProximityVoltage-ProximityVoltageTolerance*2) and (Proximity):
			Proximity=False
			ProximityLostTime=time()
			TimeStampedPrint("plug removed\n\n\n")
			TimeStampedPrint('Proximity Voltage: '+str(TheOutputVoltage))

			BigStatus='Charge Cable Removed'
			SmallStatus=''
			sleep(2)
			BigStatus='Insert Charge Cable Into Car'
			SmallStatus='Waiting For Charge Cable To Be Inserted'

			#reset the values of current and voltage....actually, may not be needed here anymore ? need to remove and test.
			Volts	=	None
			Amps	=	None

			SWCAN_Relay.off()



		try:
			#have to reference each time because the slave is destroyed and created if disconnected, and sometimes it disconnects
			Volts=TWCManager.master.slaveTWCs[myTWCID].voltsPhaseA
			Amps=TWCManager.master.slaveTWCs[myTWCID].reportedAmpsActual
		except:
			Volts=-99
			Amps=-99




		if Proximity:

			message = SWCAN.recv(timeout=.075)

			if PowerKilled:
				BigStatus='Stopped Charging'
				ChargeStartTime=-1		#makes stop counting charge time even through there is still proximity

			else:

				if (Volts is not None) and (Amps is not None):
#need to do more rigorous testing of a stable connection to the TWC above instead before getting to this point. especially since None can be reset to somethign else like -99.
					PreviousTime=CurrentTime
					CurrentTime=time()
					deltaT=(CurrentTime-PreviousTime)/3600		#hours, small error on first loop when SWCANActive is initially True

					EnergyDelivered+=deltaT*Volts*Amps		#W*hours


				if OfferAccepted:

						if PendingInvoice:

							#check to see if the current invoice has been paid
							try:
								TimeStampedPrint("trying to check the current invoice's payment status")
								OutstandingInvoiceStatus=lnd.lookup_invoice(OutstandingInvoice.r_hash)
								TimeStampedPrint("checked the current invoice's payment status")
								if OutstandingInvoiceStatus.settled:
									EnergyPaidFor+=OutstandingInvoiceStatus.value/(CurrentRate)		#W*hours
									PendingInvoice=False
									InitialInvoice=False							#reset every time just to make the logic simpler

									TimeStampedPrint("payment received, time since last payment received="+str(time()-LastPaymentReceivedTime)+"s")
									ChargeTimeText=FormatTimeDeltaToPaddedString(timedelta(seconds=round((datetime.now()-ChargeStartTime).total_seconds())))	#round to the nearest second, then format as a zero padded string
									TimeStampedPrint('WhoursDelivered: '+RoundAndPadToString(EnergyDelivered,1)+',   Volts: '+RoundAndPadToString(Volts,2)+',   Amps: '+RoundAndPadToString(Amps,2)+',   ChargeSessionTime: '+ChargeTimeText)

									LastPaymentReceivedTime=time()

									SmallStatus='Payment Received'
							except:
								TimeStampedPrint("tried checking the current invoice's payment status but there was probably a network connection issue")
								sleep(.25)


						#now that the pending invoices have been processed, see if it's time to send another invoice, or shutdown power if invoices haven't been paid in a timely manner.

						#time to send another invoice
						#adjust multiplier to decide when to send next invoice. can really send as early as possible because car just waits until it's really time to make a payment.
						#was 0.5, but higher is probably really better because don't know how long the lightning network payment routing is actually going to take.
						#send payment request 2*90% ahead of time so the buyer can have it ready in case they have a poor internet connection and want to pay early to avoid disruptions.
						#note, because below 1% error is allowed, this test may actually not have much meaning considering over the course of a charging cycle
						#the total error may be larger than an individual payment amount, so EnergyPaidFor-EnergyDelivered is likely less than 0 and therefor
						#a new invoice will just be sent right after the previous invoice was paid, rather than waiting.
						if ((EnergyPaidFor-EnergyDelivered)<RequiredPaymentAmount*2*0.90) and not PendingInvoice:
							RequiredPaymentAmount=WhoursPerPayment*CurrentRate				#sat

							try:
								TimeStampedPrint("trying to get an invoice")
								OutstandingInvoice=lnd.add_invoice(RequiredPaymentAmount)
								TimeStampedPrint("got an invoice")

								#need to add a try except here, because the buyer may not be listening properly!!!!!!!!!!!!
								SWCAN_ISOTP.send(OutstandingInvoice.payment_request.encode())			#send the new invoice using CAN ISOTP
								TimeStampedPrint("sent new invoice for "+str(RequiredPaymentAmount)+" satoshis")
								SmallStatus='Payment Requested'

								PendingInvoice=True

							except:
								TimeStampedPrint("tried getting a new invoice but there was probably a network connection issue")
								sleep(.25)


						elif PendingInvoice:									#waiting for payment
							#TimeStampedPrint("waiting for payment, and limit not yet reached")
							pass

						else:
							#TimeStampedPrint("waiting to send next invoice")
							pass



				else:
					#try to negotiate the offer
					if (message is not None) and (message.arbitration_id == 1999 and message.data[0]==1):		#don't really need to convert to int since hex works fine for a 0 vs 1

						try:
							FirstRequiredPaymentAmount=1*RequiredPaymentAmount				#sat, adjust multiplier if desire the first payment to be higher than regular payments.
							TimeStampedPrint("trying to get first invoice")
							OutstandingInvoice=lnd.add_invoice(FirstRequiredPaymentAmount)
							TimeStampedPrint("got first invoice")

							#buyer accepted the rate
							OfferAccepted=True
							TimeStampedPrint("buyer accepted rate")

							ChargeStartTime=datetime.now()

							BigStatus='Charging'
							SmallStatus='Sale Terms Accepted'

							SWCAN_ISOTP.send(OutstandingInvoice.payment_request.encode())
							TimeStampedPrint("sent first invoice for "+str(FirstRequiredPaymentAmount)+" satoshis")

							PendingInvoice=True
						except:
#probably the protocol will get stuck if this exception is caught because the buyer won't re-send the acceptance message. maybe need buyer to keep repeating the acceptance message until the seller sends an acknowledgement???
							TimeStampedPrint("tried getting a new (first) invoice but there was probably a network connection issue")
							sleep(.25)

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

						LastPaymentReceivedTime=time()			#fudged since no payment actually received yet, but want to still time since invoice sent, and need variable to be initialized.


				if (
						#buyer must pay ahead 20% for all payments but the first payment (must pay after 80% has been delivered).
						#also allow 1% error due to measurement error as well as transmission losses between the car and the wall unit.
						#this error basically needs to be taken into consideration when setting the sale rate.
						(((EnergyPaidFor-EnergyDelivered*0.99)<WhoursPerPayment*0.20)	and not	InitialInvoice)

							or

						#buyer can go into debt 30% before the first payment, also allowing for 1% error as above, although that may be really needed for the first payment.
						(((EnergyPaidFor-EnergyDelivered*0.99)<-WhoursPerPayment*0.30)	and	InitialInvoice)
					):

					TimeStampedPrint("buyer never paid, need to kill power, time since last payment received="+str(time()-LastPaymentReceivedTime)+"s")
					PowerKilled=True		#need to be smarter and make sure power is actually killed (monitor amps is one way) because it doesn't always seem to work. maybe it doesn't always work because need to also add myTWCID to the following command (and actually, should consider adding it above in some other commands as well?)?
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

	# the state should be restored to off when python is stopped, but explicitly set to off to be sure.
	SWCAN_Relay.off()

	TimeStampedPrint("turned off relay\n\n\n")




