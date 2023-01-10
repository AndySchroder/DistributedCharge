#!/usr/bin/env python3


###############################################################################
###############################################################################
# Copyright (c) 2023, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################


print('')
print('')
print('')
print('')


################################################################
# import modules
################################################################

from ekmmeters import SerialPort,V4Meter		#needs to go first because it has some funky time module that is imported, otherwise need to only import what is used instead of using * --- UPDATE: now importing only what is needed too.

from time import sleep,time
from datetime import datetime,timedelta

from lndgrpc import LNDClient
from GUI import GUIThread as GUI
from common import StatusPrint,UpdateVariables,TheDataFolder,WaitForTimeSync,TimeStampedPrintAndSmallStatusUpdate
from yaml import safe_load
from helpers2 import FormatTimeDeltaToPaddedString,RoundAndPadToString,TimeStampedPrint,FullDateTimeString,SetPrintWarningMessages

from gpiozero import LED


import sys,json,socket,ssl



from pathlib import Path

from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from SocketHelpers import SendMessage,ReceiveMessage
from secrets import token_bytes






################################################################


# TODO:
#  - make more constraints on payments because if PrePayment and RequiredPaymentAmount are too small for the current power level, there is a chance that the invoice won't be requested quick enough and then paid quick enough and then power will be shut off even when the buyer wanted to pay invoices as soon as they were received.







################################################################
# import values from config file
################################################################

with open(TheDataFolder+'Config.yaml', 'r') as file:
	ConfigFile=safe_load(file)

# assign some shorter variable names
LocalMeterNumber=ConfigFile['Seller']['LocalMeterNumber']
LocalMeterScalingFactor=ConfigFile['Seller']['LocalMeterScalingFactor']

# need to use the function so that it can modify the value inside the imported module so that everything that imports TimeStampedPrint will get this value.
SetPrintWarningMessages(ConfigFile['Seller']['PrintWarningMessages'])

################################################################


TimeStampedPrint('startup!')			#needs to be after loading configuration since TimeStampedPrint needs to know the value of PrintWarningMessages
TimeStampedPrint('configuration loaded')

################################################################

# launch the GUI before anything gets printed to standard output
GUI.start()			#starts .run() (and maybe some other stuff?)

WaitForTimeSync(GUI)

# uncomment to add a pause if doing a screen record and need time to organize windows to the right size before anything gets printed to standard output.
#sleep(120)

################################################################

from RateFunctions import GenerateCurrentSellOfferTerms,MeterMonitor	#uses TimeStampedPrint, so do this import away from the rest of the modules


################################################################














################################################################
# initialize variables
################################################################



OfferAccepted=False
PowerKilled=True

LastPaymentReceivedTime=0

RequiredPaymentAmount=-1

TimeLastOfferSent=time()



################################################################








################################################################
# read in certificates
################################################################

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(TheDataFolder+'/SSL/cert.pem', TheDataFolder+'/SSL/key.pem')

with open(TheDataFolder+'/SSL/cert.pem', "rb") as f:
	cert_obj = load_pem_x509_certificate(f.read(),default_backend())	# can't figure out how to extract this from the context object created above, so just read it in twice. hard to follow the source code because it is a python module written in c(++?, https://raw.githubusercontent.com/python/cpython/main/Modules/_ssl.c). it seems like python doesn't have access to all variables in the module.
h=cert_obj.fingerprint(hashes.SHA256())
TimeStampedPrint('fingerprint client needs to trust: '+h.hex())


################################################################




################################################################
# initialize GPIO
################################################################

Contactor = LED(27)

#should be off on boot, but just make sure it is off on startup in case the script crashed/killed with it on and is being restarted without rebooting.
Contactor.off()
GUI.BigStatus='Power OFF'

################################################################




################################################################
#initialize the LND RPC
################################################################

lnd = LNDClient(ConfigFile['Seller']['LNDhost'], network=ConfigFile['Seller']['LNDnetwork'], macaroon_filepath=TheDataFolder+'/lnd/invoice.macaroon',cert_filepath=TheDataFolder+'/lnd/tls.cert')

################################################################





################################################################
#initialize the RS-485 port and meter
################################################################


#ekm_set_log(ekm_print_log)
MeterPort = SerialPort(ConfigFile['Seller']['RS485Port'])
MeterPort.initPort()
RawMeter = V4Meter(LocalMeterNumber)
RawMeter.attachPort(MeterPort)


################################################################



Meter=MeterMonitor(RawMeter,LocalMeterScalingFactor,ForceInitialRead=True)
UpdateVariables(Meter,GUI,'seller')







try:

	with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
		sock.bind(('0.0.0.0', 4545))
		sock.listen(5)		# TODO: figure out why this is needed.
		TimeStampedPrintAndSmallStatusUpdate('Waiting for buyer to establish communication link.',GUI)
		with context.wrap_socket(sock, server_side=True) as ssock:
			ClientAuthenticated=False
			conn, addr = ssock.accept()
			server_cert = conn.getpeercert(binary_form=True);

			with conn:
				TimeStampedPrintAndSmallStatusUpdate('Communication link established.',GUI)
				TimeStampedPrint(f"Connected by {addr}")

				InitialInvoice=True
				OfferAccepted=False
				PowerKilled=True
				PaymentsReceived=0
				SalePeriods=0

				while True:

					if (PowerKilled and GUI.ChargeStartTime!=-1):
						GUI.ChargeStartTime=-1		#makes stop counting charge time even through there is still proximity. might need to rework this since proximity isn't relevant in the GRID application?????????

					else:

						NewMessage = ReceiveMessage(conn)

						if not ClientAuthenticated:
							if not NewMessage:
								break
							if NewMessage == "I don't trust you.":
								TimeStampedPrint('client thinks there is a man in the middle attack and will disconnect')
								break
							elif NewMessage == ConfigFile['Seller']['RemoteClientIdentifier']:
								ClientAuthenticated=True
								GUI.Connected=ClientAuthenticated

								SendMessage('client is allowed to connect',conn)
								TimeStampedPrintAndSmallStatusUpdate('Buyer Authenticated',GUI)
							else:
								SendMessage('Client Identifier not allowed, disconnecting',conn)
								break
						else:		#client is authenticated

							#after authenticating, everything should be JSON unless ACK

							MessageAlreadySentThisLoopIteration=False

							#try to negotiate the offer

							if (NewMessage=='ACK') and (not OfferAccepted or (SellOfferTerms['OfferStopTime']-time())<30):

								#provide the offer

								#prepare to compute energy paid for and also to map the rate profile to the actual offer duration
								#on the buyer's side, they put the RequiredRateInterpolator object inside the SellOfferTerms dictionary, but that is fine because it's just their personal dictionary,
								#but since this one will be converted to JSON and send remotely, don't want to do that.
								NewSellOfferTerms,NewRequiredRateInterpolator=GenerateCurrentSellOfferTerms()

								# add some keys and values.
								NewSellOfferTerms['MessageType']='SellOfferTerms'
								NewSellOfferTerms['MessageReference']=token_bytes(32).hex()			#random data to make the message unique.
								NewSellOfferTerms['MeterNumber']=LocalMeterNumber	# integer,	Confirmation that the buyer and seller are talking about the same meter.

								if not OfferAccepted:
									NewSellOfferTerms['SellOfferTermsType'] = 'Initial'

									if 'InitialDeposit' in NewSellOfferTerms['Payments']:
										# sat,	integer, this is basically a minimum amount of business the seller is willing to do.
										# If the InitialDeposit is less than the PrePayment then it doesn't have any impact and the PrePayment will be used for the first payment.
										NewSellOfferTerms['Payments']['InitialDeposit']=max(NewSellOfferTerms['Payments']['InitialDepositMultiple']*NewSellOfferTerms['Payments']['MinPayment'],NewSellOfferTerms['Payments']['PrePayment'])
									else:
										#if no initial deposit defined, then set it to the prepayment amount.
										NewSellOfferTerms['Payments']['InitialDeposit']=NewSellOfferTerms['Payments']['PrePayment']

									LastPaymentReceivedTime=time()			#fudged since no payment actually received yet, but want to still time since invoice sent, and need variable to be initialized.
								elif (SellOfferTerms['OfferStopTime']-time())<30:	#note: this is checking the old offer
									NewSellOfferTerms['SellOfferTermsType'] = 'Renewal'
								else:
									raise Exception('should never get here')

								# remove some keys and values that aren't needed buy the buyer. don't want to confuse them or provide them with unnecessary information
								NewSellOfferTerms['Payments'].pop('InitialDepositMultiple')
								# anything else to add ????

								GUI.SmallStatus='Provided '+NewSellOfferTerms['SellOfferTermsType']+' Offer'

								TimeStampedPrint(NewSellOfferTerms,prettyprintprepend='NewSellOfferTerms',prettyprint=True)

								SendMessage(json.dumps(NewSellOfferTerms),conn)
								OfferAccepted=False
								MessageAlreadySentThisLoopIteration=True

							elif NewMessage=='ACK' and OfferAccepted:

								if PendingInvoice:

									#check to see if the current invoice has been paid
									try:
										TimeStampedPrint("trying to check the current invoice's payment status")
										OutstandingInvoiceStatus=lnd.lookup_invoice(OutstandingInvoice.r_hash)
										TimeStampedPrint("checked the current invoice's payment status")
										if OutstandingInvoiceStatus.settled:

											Meter.EnergyPayments+=OutstandingInvoiceStatus.value
											PaymentsReceived+=1

											PendingInvoice=False

											if InitialInvoice:
												GUI.ChargeStartTime=datetime.now()
												Contactor.on()
												PowerKilled=False
												GUI.BigStatus='Power ON'

											InitialInvoice=False							#reset every time just to make the logic simpler

											TimeStampedPrint("payment received, time since last payment received="+str(time()-LastPaymentReceivedTime)+"s")

											StatusPrint(Meter,GUI,SellOfferTerms,PaymentsReceived,SalePeriods)

											LastPaymentReceivedTime=time()

											GUI.SmallStatus='Payment Received - '+FullDateTimeString(datetime.now())	#need to check and see if the LND GRPC gives an official time instead of this one.
									except:
										TimeStampedPrint("tried checking the current invoice's payment status but there was probably a network connection issue")
										sleep(.25)
										raise


								# now that the pending invoices have been processed, see if it's time to send another invoice, or shutdown power if invoices haven't been paid in a timely manner.

								# time to send another invoice #

								# adjust multiplier to decide when to send next invoice. can really send as early as possible because the buyer just waits until it's really time to make a payment.
								# was intially using 0.5, but higher is probably really better because don't know how long the lightning network payment routing is actually going to take.
								# so, send payment request 2*90% ahead of time so the buyer can have it ready in case they have a poor internet connection and want to pay early to avoid disruptions.

								if ((Meter.EnergyPayments-Meter.EnergyCost)<SellOfferTerms['Payments']['PrePayment']*2*0.60) and not PendingInvoice:
									try:
										TimeStampedPrint("trying to get an invoice")
										OutstandingInvoice=lnd.add_invoice(RequiredPaymentAmount)
										TimeStampedPrint("got an invoice")


										SellerInvoice = 	{
													'MessageType':		'SellerInvoice',
													'Invoice':		OutstandingInvoice.payment_request,		#lightning invoice string
																						#don't need a MessageReference because the Invoice should be unique
													}
										SendMessage(json.dumps(SellerInvoice),conn)
										MessageAlreadySentThisLoopIteration=True


										TimeStampedPrint("sent new invoice for "+str(RequiredPaymentAmount)+" satoshis")
										GUI.SmallStatus='Payment Requested'

										PendingInvoice=True
										HeartBeatsSinceLastStatusPrint=0

									except:
										TimeStampedPrint("tried getting a new invoice but there was probably a network connection issue")
										sleep(.25)
										raise


								elif PendingInvoice:									#waiting for payment
									TimeStampedPrint("waiting for payment, and limit not yet reached")
									# TODO: add StateMessage sends here.
									pass

								else:
									TimeStampedPrint("waiting to send next invoice")
									HeartBeatsSinceLastStatusPrint+=1
									if HeartBeatsSinceLastStatusPrint==6:
										StatusPrint(Meter,GUI,SellOfferTerms,PaymentsReceived,SalePeriods)
										HeartBeatsSinceLastStatusPrint=0
									sleep(10)		# TODO: make this sleep time more intellegent based on expected max power level and the payment size.

							elif NewMessage=='':
								TimeStampedPrint('seems like the client disconnected')
								break

							else:
								NewMessageJSON=json.loads(NewMessage)

								TimeStampedPrint(NewMessageJSON,prettyprintprepend='New JSON Received',prettyprint=True)
								if NewMessageJSON['MessageType']=='BuyerResponse':
									if OfferAccepted is True:

										# extra messages can come in because HeartBeats are used to "bump" the loop. if the duplicate message is not ignored, then the offer will be
										# accepted many times and new invoices created each time, but the invoices can never be checked because they keep changing (probably because
										# old ones are forgotten and there is no invoice queue???), so the logic above can never look at the right one and see if it was paid.

										TimeStampedPrint("buyer already accepted rate, ignoring duplicate message")

									else:

										if NewMessageJSON['AcceptedSellerRate']==True:
											#buyer accepted the rate
											OfferAccepted=True
											TimeStampedPrint("buyer accepted rate")
											#GUI.BigStatus=''
											GUI.SmallStatus='Sale Terms Accepted'

											HeartBeatsSinceLastStatusPrint=0
											SalePeriods+=1

											SellOfferTerms=NewSellOfferTerms
											RequiredRateInterpolator=NewRequiredRateInterpolator

											Meter.SellOfferTerms=SellOfferTerms
											Meter.RequiredRateInterpolator=RequiredRateInterpolator

											if 	(
													('DesiredPaymentSize' in NewMessageJSON)

														and

													#see https://docs.python.org/3/reference/expressions.html#comparisons for why this works.
													(SellOfferTerms['Payments']['MinPayment']<NewMessageJSON['DesiredPaymentSize']<SellOfferTerms['Payments']['MaxPayment'])
												):

												#buyer's desired payment size is within limits, so use it except for the intial invoice.
												RequiredPaymentAmount=NewMessageJSON['DesiredPaymentSize']
											else:
												#buyer did not specify a desired payment size or it was out of the allowable limits, so use the smallest payment size allowable.
												RequiredPaymentAmount=SellOfferTerms['Payments']['MinPayment']

											GUI.RequiredPaymentAmount=RequiredPaymentAmount
											GUI.MaxAmps=SellOfferTerms['Electrical']['Current']['Maximum']

											try:
												if SellOfferTerms['SellOfferTermsType']=='Initial':
													TimeStampedPrint("trying to get first invoice")

													OutstandingInvoice=lnd.add_invoice(SellOfferTerms['Payments']['InitialDeposit'])

													TimeStampedPrint("got first invoice")

													SellerInvoice = 	{
																'MessageType':		'SellerInvoice',
																'Invoice':		OutstandingInvoice.payment_request,			#lightning invoice string
																							#don't need a MessageReference because the Invoice should be unique
																}
													SendMessage(json.dumps(SellerInvoice),conn)
													MessageAlreadySentThisLoopIteration=True

													TimeStampedPrint("sent first invoice for "+str(SellOfferTerms['Payments']['InitialDeposit'])+" satoshis")

													PendingInvoice=True

											except:
												# probably the protocol will get stuck if this exception is caught because the buyer won't re-send the acceptance message.
												# maybe need buyer to keep repeating the acceptance message until the seller sends an acknowledgement???
												TimeStampedPrint("tried getting a new (first) invoice but there was probably a network connection issue")
												sleep(.25)

												raise

										else:
											OfferAccepted=False
											TimeStampedPrint("buyer rejected rate")
											#GUI.SmallStatus='Sale Terms Rejected'
											sleep(5)			#don't loop and waste CPU time, instead wait and give the buyer a chance to change their mind.

								else:
									#TODO: decide if need to take better action here. if not, everything just stalls? currently just raising an exception because need to decide what to do.
									raise Exception("some other message was received")



							if not MessageAlreadySentThisLoopIteration:		#other logic makes this not necessary, but this can speed things up especially since rejected offers have a long sleep time.
								SendMessage('HeartBeat',conn)			#send heartbeat message to see how stable the connection is and also to "bump" the loop on since currently having read blocks on the socket.



						if	(
								(not PowerKilled)												# energy has already started being delivered.
									and
								(
									(
										((Meter.EnergyPayments-Meter.EnergyCost)<SellOfferTerms['Payments']['PrePayment']*0.20)		# buyer didn't pay ahead 20% for all payments (they must pay after 80% has been delivered).
									)
										or (SellOfferTerms['OfferStopTime']<time())							# current sale period has expired without being renewed.

								)
							):

							TimeStampedPrint("buyer never paid or didn't renew payment terms, need to kill power, time since last payment received="+str(time()-LastPaymentReceivedTime)+"s EnergyPayments="+str(Meter.EnergyPayments)+' EnergyCost='+str(Meter.EnergyCost))
							Contactor.off()
							PowerKilled=True
							GUI.BigStatus='Power OFF'
							GUI.SmallStatus='Customer Did Not Make Payment'

						elif (not PowerKilled) and (Meter.Amps>SellOfferTerms['Electrical']['Current']['Maximum']):
							Contactor.off()
							PowerKilled=True
							TimeStampedPrint('buyer tried consuming too much current, shutting down before blowing the circuit breaker, PowerKilled='+str(PowerKilled))
							GUI.BigStatus='Power OFF'
							GUI.SmallStatus='Current draw greater than allowed.'

						else:
							# everything is okay, continue to allow energy flow
							pass





					sleep(0.075)



except (KeyboardInterrupt, SystemExit):


	GUI.stop()
	GUI.join()	#for some reason if this is not used, python tries too quit before the stop command is received by the thread and it gracefully shutdown and then it takes longer for tk to timeout and close the interpreter?

	TimeStampedPrint("quitting")

except:
	raise

finally:

	# the state should be restored to off when python is stopped, but explicitly set to off to be sure.
	Contactor.off()

	TimeStampedPrint("turned off relay\n\n\n")




