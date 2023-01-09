#!/usr/bin/env python3


###############################################################################
###############################################################################
# Copyright (c) 2023, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################




################################################################
# import modules
################################################################

from ekmmeters import SerialPort,V4Meter		#needs to go first because it has some funky time module that is imported, otherwise need to only import what is used instead of using * --- UPDATE: now importing only what is needed too.

from time import sleep,time
from datetime import datetime,timedelta

from lndgrpc import LNDClient
from GUI import GUIThread as GUI
from common import StatusPrint,UpdateVariables,TheDataFolder,WaitForTimeSync
from yaml import safe_load
from helpers2 import FormatTimeDeltaToPaddedString,RoundAndPadToString,TimeStampedPrint,FullDateTimeString,SetPrintWarningMessages

from gpiozero import LED
from collections import deque

import sys,json,socket,ssl



from pathlib import Path

from cryptography.x509 import load_der_x509_certificate
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from SocketHelpers import SendMessage,ReceiveMessage
from secrets import token_bytes

from zmq import Context,PUB
from copy import deepcopy



################################################################


# TODO:
#  - penalize the seller if they don't stay with the voltage limits that they guaranteed.









################################################################
# import values from config file
################################################################

with open(TheDataFolder+'Config.yaml', 'r') as file:
	ConfigFile=safe_load(file)

# assign some shorter variable names
LocalMeterNumber=ConfigFile['Buyer']['LocalMeterNumber']
LocalMeterScalingFactor=ConfigFile['Buyer']['LocalMeterScalingFactor']

# need to use the function so that it can modify the value inside the imported module so that everything that imports TimeStampedPrint will get this value.
SetPrintWarningMessages(ConfigFile['Buyer']['PrintWarningMessages'])

################################################################


print('')
print('')
TimeStampedPrint('startup!')			#needs to be after loading configuration since TimeStampedPrint needs to know the value of PrintWarningMessages
TimeStampedPrint('configuration loaded')

################################################################

# launch the GUI before anything gets printed to standard output
GUI.start()			#starts .run() (and maybe some other stuff?)

WaitForTimeSync(GUI)

# uncomment to add a pause if doing a screen record and need time to organize windows to the right size before anything gets printed to standard output.
#sleep(120)

################################################################

from RateFunctions import SetInterpolator,CheckRateAllowable,MeterMonitor,RateFile		#uses TimeStampedPrint, so do this import away from the rest of the modules


################################################################







################################################################
# initialize variables
################################################################


AcceptedRate=False
TotalWhoursCharged=-1
RequiredPaymentAmount=0


################################################################











def CheckSellOfferTerms(BuyOfferTerms,SellOfferTerms):
#need to make it check and report all non accepted terms, not just the first one found.

	if SellOfferTerms['Payments']['MinPayment']					>  BuyOfferTerms['Payments']['MaxPayment']:
		TimeStampedPrint('Smallest payment seller is willing to accept is larger than the largest payment willing to make')
		return False
	elif SellOfferTerms['Payments']['MaxPayment']						<  BuyOfferTerms['Payments']['MinPayment']:
		TimeStampedPrint('Largest payment seller is willing to accept is smaller than the smallest payment willing to make')
		return False
	elif SellOfferTerms['Payments']['PrePayment']						>  BuyOfferTerms['Payments']['MaxPrePayment']:
		TimeStampedPrint('Requested PrePayment is too high.')
		return False

	elif not CheckRateAllowable(BuyOfferTerms,SellOfferTerms):
		TimeStampedPrint('Requested Rate profile is too high.')
		return False

	elif (SellOfferTerms['SellOfferTermsType']=='Renewal') and ('InitialDeposit' in SellOfferTerms['Payments']) and (SellOfferTerms['Payments']['InitialDeposit'] > 0):
		TimeStampedPrint('no InitialDeposit required after initial sale terms accepted.')
		return False
	elif ('InitialDeposit' in SellOfferTerms['Payments']) and (SellOfferTerms['Payments']['InitialDeposit'] >  BuyOfferTerms['Payments']['MaxInitialDeposit']):
		TimeStampedPrint('Requested InitialDeposit is too high.')
		return False
	elif SellOfferTerms['Electrical']['Current']['Maximum']				<  BuyOfferTerms['Electrical']['Current']['MaximumRequired']:
		TimeStampedPrint('MaxCurrent is too low')
		return False
	elif SellOfferTerms['Electrical']['Voltage']['Maximum']				>  BuyOfferTerms['Electrical']['Voltage']['MaximumAllowed']:
		TimeStampedPrint('Max guaranteed voltage is too high')
		return False
	elif SellOfferTerms['Electrical']['Voltage']['Minimum']				<  BuyOfferTerms['Electrical']['Voltage']['MinimumAllowed']:
		TimeStampedPrint('Min guaranteed voltage is too low')
		return False
	elif SellOfferTerms['MeterNumber']						!= ConfigFile['Buyer']['RemoteMeterNumber']:
		TimeStampedPrint('Not in agreement in the meter being paid')
		return False
	elif (SellOfferTerms['OfferStopTime'] - SellOfferTerms['OfferStartTime'])	>  BuyOfferTerms['Duration']['MaxTime']:
		TimeStampedPrint('Duration of the SellOffer too long.')
		return False
	elif (SellOfferTerms['OfferStopTime'] - SellOfferTerms['OfferStartTime'])	<  BuyOfferTerms['Duration']['MinTime']:
		TimeStampedPrint('Duration of the SellOffer too short.')
		return False
	else:
		TimeStampedPrint('All SellOfferTerms accepted.')
		return True


################################################################



################################################################
#initialize the LND RPC
################################################################

lnd = LNDClient(ConfigFile['Buyer']['LNDhost'], network=ConfigFile['Buyer']['LNDnetwork'], macaroon_filepath=TheDataFolder+'/lnd/admin.macaroon',cert_filepath=TheDataFolder+'/lnd/tls.cert')

################################################################


InvoiceQueue=deque()








SSLcontext			= ssl.SSLContext(ssl.PROTOCOL_SSLv23);
SSLcontext.verify_mode		= ssl.CERT_NONE;


################################################################
#initialize the RS-485 port and meter
################################################################


#ekm_set_log(ekm_print_log)
MeterPort = SerialPort(ConfigFile['Buyer']['RS485Port'])
MeterPort.initPort()
RawMeter = V4Meter(LocalMeterNumber)
RawMeter.attachPort(MeterPort)


################################################################







################################################################
# zmq setup
################################################################

# note, this connection is not secure, but it's assumed okay for now because it should only be used on a local network

ZMQcontext = Context()
ZMQsocket = ZMQcontext.socket(PUB)
ZMQsocket.bind("tcp://*:5555")

################################################################





Meter=MeterMonitor(RawMeter,LocalMeterScalingFactor)
UpdateVariablesThread=UpdateVariables(Meter,GUI,'buyer',ZMQsocket)







try:
	while True:
		try:
			AcceptedRate=False
			PaymentsReceived=0
			SalePeriods=0		# might want to use this variable instead of Meter.EnergyPayments to test for the first sale period now?
			with socket.create_connection((ConfigFile['Buyer']['RemoteHost'], 4545)) as sock:
				with SSLcontext.wrap_socket(sock, server_hostname=ConfigFile['Buyer']['RemoteHost']) as ssock:		#?????????? why RemoteHost needed again?????????????????
					ServerAuthenticated=False
					while True:
						if not ServerAuthenticated:
							server_cert = ssock.getpeercert(binary_form=True);
							cert_obj = load_der_x509_certificate(server_cert,default_backend())
							h=cert_obj.fingerprint(hashes.SHA256())
							if ConfigFile['Buyer']['RemoteFingerPrintToTrust'] == h.hex():
								TimeStampedPrint('server authenticated')

								TimeStampedPrint(ssock.version())

								SendMessage(ConfigFile['Buyer']['LocalClientIdentifier'],ssock)

								# if PrintWarningMessages=True this will print the response from the server.
								NewMessage=ReceiveMessage(ssock)

								# if the server disconnects, that will break this script when the ACK is sent back next, so no other tests needed.
								SendMessage("ACK",ssock,EchoPrint=False)

								ServerAuthenticated=True
								GUI.Connected=ServerAuthenticated

								# TODO: after authenticating, might want to allow the buyer request their current and energy demands first, then get a bid from the seller.

							else:
								TimeStampedPrint('server did not authenticate properly')
								SendMessage("I don't trust you.",ssock)
								break

						else:		#keep receiving new messages
							NewMessage=ReceiveMessage(ssock)

							if NewMessage!='HeartBeat':########simler way to do this step??????????????????
								NewMessageJSON=json.loads(NewMessage)
								TimeStampedPrint(NewMessageJSON,prettyprintprepend='New JSON Received',prettyprint=True)


							if NewMessage=='HeartBeat':
								SendMessage("ACK",ssock,EchoPrint=False)

								HeartBeatsSinceLastStatusPrint+=1
								if HeartBeatsSinceLastStatusPrint==6:
									StatusPrint(Meter,GUI,SellOfferTerms,PaymentsReceived,SalePeriods,BuyOfferTerms['RateInterpolator'])
									HeartBeatsSinceLastStatusPrint=0

							elif (AcceptedRate) and (NewMessageJSON['MessageType']=='SellOfferTerms') and (SellOfferTerms['OfferStopTime']-time())>40:
								#extra messages can come in because HeartBeats used to "bump" the loop. if this is not ignored, then the offer will be accepted many times.
								TimeStampedPrint("already accepted rate and not yet time to renew rates, ignoring duplicate message")

							elif (NewMessageJSON['MessageType']=='SellOfferTerms'):		#the rate structure is either not accepted, or accepted but about to be expired

								NewSellOfferTerms=NewMessageJSON

								GUI.SmallStatus=NewSellOfferTerms['SellOfferTermsType']+' Offer Received'		#probably never seen because the following goes by too fast

								# create interpolators for checking to see if the rate is acceptable, and then for using to compute actual rates while metering.
								# don't want to combine these steps with CheckRateAllowable, because want that function to return only a True or False.

								# this should match the same functions that the seller created on their end. could have pickled it and sent that instead of JSON,
								# but everyone won't necessarily use this python implementation and also it is a security risk
								NewSellOfferTerms['InterpolationTableTimes'],NewSellOfferTerms['RateInterpolator']=SetInterpolator(NewSellOfferTerms['Rate'],NewSellOfferTerms['OfferStartTime'],NewSellOfferTerms['OfferStopTime'])

								# note, the buyer uses the start and stop time that the buyer specifies. the buyer doesn't have any expicit times defined, only a max time and a min time duration.
								# the rate profiles are relative to the beginning of the current day and year
								# however, the sellers start and stop time here are needed for setting up the interpolator because need to set them up so that they are defined relative to the start of the current day and year.
								# the BuyOfferTerms may have changed in RateFile.yaml, so re-read it now. The file can be changed and re-read multiple times, but will only be re-considered now. all other intermediate changes
								# and re-reads are essentially ignored. any changes after this time are ignored until the next sale period's offer is negotiated.
								# need to use deepcopy because RateFile.yaml isn't always changed everytime a new sale period starts, so a new Data object isn't always created,
								# so need to force creating a new one here since some things are added/changed and need it to be fresh. For example, once ExtendedRateValues creates InterpolationTableValues,
								# but don't want to re-use InterpolationTableValues again for the next period because it is for the old time range.
								BuyOfferTerms=deepcopy(RateFile.Data['BuyOfferTerms'])
								BuyOfferTerms['InterpolationTableTimes'],BuyOfferTerms['RateInterpolator']=SetInterpolator(BuyOfferTerms['Rate'],NewSellOfferTerms['OfferStartTime'],NewSellOfferTerms['OfferStopTime'])


								# print the allowed rate and the required rate since it isn't saved otherwise.
								TimeStampedPrint(NewSellOfferTerms,prettyprintprepend='NewSellOfferTerms',prettyprint=True)
								TimeStampedPrint(BuyOfferTerms,prettyprintprepend='BuyOfferTerms',prettyprint=True)


								if	(
										CheckSellOfferTerms(BuyOfferTerms,NewSellOfferTerms)					# offer terms are acceptable
											and
										(
											(Meter.EnergyPayments==0 and NewSellOfferTerms['SellOfferTermsType']=='Initial')
												or									# inital and renewal offers are used at the right time
											(Meter.EnergyPayments>0 and NewSellOfferTerms['SellOfferTermsType']=='Renewal')
										)
									):

									# after checking allowable, BuyOfferTerms no longer used. see also, notes in XXXXXXXXXXXXXXXXXXXXXXXx about how the SellOfferTerms are in force when errors are concerned.

									InvoiceQueue.clear()		# all previous invoices are no longer be valid as far as the buyer is concerned, so ignore them
									AcceptedRate=True

									HeartBeatsSinceLastStatusPrint=0
									SalePeriods+=1

									#TimeStampedPrint('getting ready to accept an offer')

									BuyerResponse =		{
												'MessageType':				'BuyerResponse',
												'AcceptedSellerRate':			True,				# True or False,	if False, the buyer can propose values that they would
																					# be willing to accept in additional fields (not yet implemented).
												'MessageReference':			token_bytes(32).hex(),		#random data to make the message unique.
												}
									if 'DesiredPaymentSize' in BuyOfferTerms['Payments']:
										BuyerResponse['DesiredPaymentSize']=BuyOfferTerms['Payments']['DesiredPaymentSize']


									SendMessage(json.dumps(BuyerResponse),ssock)
									SellOfferTerms=NewSellOfferTerms
									# warning, there is a short time delay from setting this and the seller realizing the new rate was acccepted and also setting their Meter to use the new rates.
									# hopefully the rate is not changing much at all at this time and the error is low. TODO: fix this to establish a forced rate overlap or set an exact transition time.
									Meter.SellOfferTerms=SellOfferTerms
									Meter.RequiredRateInterpolator=SellOfferTerms['RateInterpolator']

									if SellOfferTerms['SellOfferTermsType']=='Initial':
										TimeStampedPrint("warning: meter readings will be initially zero because power is not on on startup")
										if 'InitialDeposit' in SellOfferTerms['Payments']:
											# make sure the seller is not giving an initial deposit less than the prepayment amount.
											# might want to instead move this to CheckSellOfferTerms and just reject the offer if they've screwed up?
											# or, maybe not because it's really their loss and nothing hurting the buyer?
											# and actually, below where the intial deposit is accepted, smaller deposits are actually accepted, so maybe this logic
											# doesn't even enforce that they give an initial deposit equal to or greater than the prepayment amount?
											ActualInitialDeposit=max(SellOfferTerms['Payments']['InitialDeposit'],SellOfferTerms['Payments']['PrePayment'])
										else:
											#if no initial deposit defined, then set it to the prepayment amount.
											ActualInitialDeposit=SellOfferTerms['Payments']['PrePayment']
									else:
										# renewals should not have an initial deposit required and there should be no reference to it, but setting to a bogus value just to catch any cases where it accidentally is referenced.
										ActualInitialDeposit=-1

									TimeStampedPrint('Accepted '+SellOfferTerms['SellOfferTermsType']+' offer of Type '+SellOfferTerms['Rate']['Type'])
									GUI.SmallStatus='Accepted '+SellOfferTerms['SellOfferTermsType']+' Sale Terms'
									GUI.MaxAmps=SellOfferTerms['Electrical']['Current']['Maximum']
								else:

									AcceptedRate = False

									BuyerResponse =		{
												'MessageType':				'BuyerResponse',

												'AcceptedSellerRate':			False,					# True or False,	if False, the buyer can propose values that they would
																						# be willing to accept in additional fields (not yet implemented).

												'MessageReference':			token_bytes(32).hex(),			#random data to make the message unique.
									# TODO: add the previous MessageReference here and in all other messages so can know if a message was skipped.
												}

									SendMessage(json.dumps(BuyerResponse),ssock)

									TimeStampedPrint("rate or payment amount too high, not accepting")
									GUI.SmallStatus='Rejected Sale Terms, Waiting for a Better Offer'



							elif AcceptedRate and NewMessageJSON['MessageType']=='SellerInvoice':
								SendMessage("ACK",ssock,EchoPrint=False)
								InvoiceQueue.append(NewMessageJSON['Invoice'])
								HeartBeatsSinceLastStatusPrint=0
							else:
								raise Exception("some other message was received")



							if AcceptedRate:
								if len(InvoiceQueue)>0:		#invoices are waiting to be paid
									try:
										TimeStampedPrint("trying to decode the invoice")
										oldestInvoice=InvoiceQueue.popleft()

										# TODO: consider making timeout shorter as noted below for the other exception because it just hangs up the script and the GUI never updates while this is happening.
										AmountRequested=lnd.decode_payment_request(oldestInvoice).num_satoshis
										TimeStampedPrint("decoded the invoice")

										TimeStampedPrint("seller wants to be paid "+str(AmountRequested)+" satoshis")
										GUI.SmallStatus='Payment Requested'

										# figure out what the required payment size actually can be. this is basically the same logic as the seller uses, but it's written differently.
										if 'DesiredPaymentSize' in BuyOfferTerms['Payments']:
											RequiredPaymentAmount=min(max(SellOfferTerms['Payments']['MinPayment'],BuyOfferTerms['Payments']['DesiredPaymentSize']),SellOfferTerms['Payments']['MaxPayment'])
										else:
											RequiredPaymentAmount=SellOfferTerms['Payments']['MinPayment']

										GUI.RequiredPaymentAmount=RequiredPaymentAmount



										#allow error due to measurement error as well as transmission losses between the buyer and the seller.
										#this error basically needs to be taken into consideration when accepting the sale rate.
										AllowedError=0.025					# consider a very generous 2.5% error for the revenue grade meters.

										if (
												# check that the seller is not asking for payment before energy is delivered (but allow paying after 30% that has been paid for
												# has been delivered (70% ahead of time)).
												# UPDATE: poor internet connections (or trouble routing through the lightning network) can be very slow, so changed
												# this to 70%*2=140% ahead instead. also tolerate error, including a linear error and a fixed error that is a little
												# generous right now.
												# NOTE: the total amount paid can be more than 140% ahead because you can be at 139% and the RequiredPayment amount
												# is much greater than 1%, so you will be over, but you will never be over 239%

												((Meter.EnergyPayments-Meter.EnergyCost)<SellOfferTerms['Payments']['PrePayment']*0.70*2+Meter.EnergyDelivered*AllowedError+75)
													and
												(
													(AmountRequested<=RequiredPaymentAmount)		#not asking for too much payment
														or
													(
														(AmountRequested<=ActualInitialDeposit)
															and
														(Meter.EnergyPayments==0)			#first payment allows larger than normal payment amount.
													)
												)
											):

											if (Meter.ResponseReceived) or (Meter.EnergyPayments==0):
												try:

													TimeStampedPrint("sending payment")
													# TODO: decide if should check to make sure the "expiry" has not passed on the invoice yet before paying or does lnd do that automatically ????
													lnd.send_payment(oldestInvoice)			#seems to block code execution until the payment is routed, or fails

													GUI.SmallStatus='Payment Sent - '+FullDateTimeString(datetime.now())	#need to check and see if the LND GRPC gives an official time instead of this one.
													if Meter.EnergyPayments==0:
														GUI.ChargeStartTime=datetime.now()
														GUI.BigStatus='Power Expected'

													Meter.EnergyPayments+=AmountRequested
													PaymentsReceived+=1

													TimeStampedPrint("sent payment for "+str(AmountRequested)+" satoshis")

													StatusPrint(Meter,GUI,SellOfferTerms,PaymentsReceived,SalePeriods,BuyOfferTerms['RateInterpolator'])

												except:
													# TODO:
													#        - check the response from lnd.send_payment to see what actually happened. lnd.send_payment doesn't fail (raise a python exception)
													#          if the payment fails to route, only if lnd.send_payment can't contact the lnd node. also, as mentioned above, not sure what happens
													#          if the the invoice expires.
													#        - it is a very long time until timeout on network failure so this exception isn't caught very quickly and the GUI never updates
													#          while it is waiting. need to make the GUI update independently. UPDATE: is this fixed by the new UpdateVariablesThread ??? need to test.
													TimeStampedPrint("tried sending payment but there was probably a network connection issue")
													sleep(.25)

													raise
											else:
												InvoiceQueue.appendleft(oldestInvoice)		#put the invoice back in the queue
												TimeStampedPrint("first payment made for initial deposit, but meter not fully powered on. waiting to make next payment until power on can be confirmed.")
												sleep(1)

										else:
											#seller is asking for payment to quickly, waiting until they deliver energy that was agreed upon.
											#if they aren't happy and think they delivered enough, they will shut down.
											#currently, the buyer will tolerate up to 20% of error. the seller tolerates 30%
											#because they need to give time for a payment to actually be made.
											#need to do something if AmountRequested>RequiredPaymentAmount and EnergyPaidFor>0


											InvoiceQueue.appendleft(oldestInvoice)		#put the invoice back in the queue
											TimeStampedPrint("not yet time to pay, waiting")

									except:
										TimeStampedPrint("tried decoding the invoice but there was probably a network connection issue")
										InvoiceQueue.appendleft(oldestInvoice)		#put the invoice back in the queue

										#raise



								else:
#									TimeStampedPrint("waiting for next invoice")
									pass





		except:
			#TODO: need to make this exception chatching more specific. more can happen than just closing of the connection
			TimeStampedPrint("server closed connection")
			raise		#uncomment this line so can force the Launcher script to restart the entire program after every disconnect (useful when debugging because only need to kill the server)
							

		sleep(0.5)




except (KeyboardInterrupt, SystemExit):


	GUI.stop()
	GUI.join()	#for some reason if this is not used, python tries too quit before the stop command is received by the thread and it gracefully shutdown and then it takes longer for tk to timeout and close the interpreter?

	TimeStampedPrint("quitting")

except:
	raise

finally:

	TimeStampedPrint("quit\n\n\n")




