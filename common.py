


###############################################################################
###############################################################################
# Copyright (c) 2022, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################




from helpers2 import RoundAndPadToString,TimeStampedPrint,FullDateTimeString,FormatTimeDeltaToPaddedString
from textwrap import indent
from threading import Thread
from SocketHelpers import PackTopicAndJSONAndSend
from time import sleep
from pathlib import Path
from datetime import datetime


# open the output file --- need to fix this so that it re-opens a new file every day, but right now, it just sticks with the file created during the time it was started up.
DataLogOutputFile = open(str(Path.home())+'/.dc/'+'DataLog-'+datetime.now().strftime('%Y.%m.%d--%H.%M.%S.%f')+'.txt', "a")


def StatusPrint(Meter,GUI,SellOfferTerms,PaymentsReceived,SalePeriods,MaxAuthorizedRateInterpolator=None):

	# want all time references to be exactly the same, so use this moment as the reference.
	CurrentTime=datetime.now()

	## write data to the console/log file for live monitoring##

	StatusMessage  = ''
	StatusMessage += 'Power: '+RoundAndPadToString(Meter.Power,0)+' W,   '
	StatusMessage += 'Volts: '+RoundAndPadToString(Meter.Volts,2)+',   '
	StatusMessage += 'Amps: '+RoundAndPadToString(Meter.Amps,2)
	StatusMessage += '\n'
	StatusMessage += 'Energy Received: '+ RoundAndPadToString(Meter.EnergyDelivered,0)+' W*hours,   '
	StatusMessage += 'Energy Cost: '+RoundAndPadToString(Meter.EnergyCost,0)+' sats'
	StatusMessage += '\n'
	StatusMessage += 'Required Rate: '+RoundAndPadToString(Meter.RecentRate*100,0)+' sat/(100 W*hour),   '
	if MaxAuthorizedRateInterpolator is not None:
		StatusMessage += 'Max Authorized Rate: '+RoundAndPadToString(MaxAuthorizedRateInterpolator(CurrentTime.timestamp())*100,0)+' sat/(100 W*hour)'
	StatusMessage += '\n'
	StatusMessage += 'Sale Period: ['
	StatusMessage += FullDateTimeString(SellOfferTerms['OfferStartTime'])+' <~~> '
	StatusMessage += FullDateTimeString(SellOfferTerms['OfferStopTime'])+'],  '
	StatusMessage += 'Remaining:'+FormatTimeDeltaToPaddedString(SellOfferTerms['OfferStopTime']-CurrentTime.timestamp())+',  '
	StatusMessage += 'Period #:'+RoundAndPadToString(SalePeriods,0)
	StatusMessage += '\n'
	StatusMessage += 'Total Payments: '+RoundAndPadToString(Meter.EnergyPayments,0)+' sats,   '
	StatusMessage += 'Number Payments: '+RoundAndPadToString(PaymentsReceived,0)+',   '
	StatusMessage += 'Session Time: '+GUI.ChargeTimeText
	StatusMessage  = '\n' + indent(StatusMessage,' '*30)	#*35)
	StatusMessage += '\n'
	TimeStampedPrint(StatusMessage)
#TODO: add some of this information to the GUI that is not already there



	## write data to a TAB delimited text file for data analysis ##

	# date_time is redundant with unix_time (but make the log file easier to read when just casually looking at it) since can use datetime.datetime.fromtimestamp(unix_time) to easily get year,month,day,hour,minute,second for doing statistics on.
	# Session Time is also provided for reference, but can be calculated by subtracting each row's unix_time from the first row's unix_time.


	DataString = ''
	DataString += RoundAndPadToString(CurrentTime.timestamp(),4,ShowThousandsSeparator=False)		+ '\t'		# unix_time
	DataString += CurrentTime.strftime('%Y.%m.%d--%H.%M.%S.%f')						+ '\t'		# date_time
	DataString += GUI.ChargeTimeText									+ '\t'		# Session Time
	DataString += RoundAndPadToString(SellOfferTerms['OfferStopTime']-CurrentTime.timestamp(),4)		+ '\t'		# Sale Period Time Remaining (seconds with thousands separator)
	DataString += RoundAndPadToString(SalePeriods,0)							+ '\t'		# Sale Period Number

	DataString += RoundAndPadToString(Meter.Power,5)							+ '\t'		# Power [W]
	DataString += RoundAndPadToString(Meter.Volts,3)							+ '\t'		# Volts
	DataString += RoundAndPadToString(Meter.Amps,3)								+ '\t'		# Amps
	DataString += RoundAndPadToString(Meter.EnergyDelivered,2)						+ '\t'		# EnergyDelivered [W*hours]

	DataString += RoundAndPadToString(Meter.RecentRate,4)							+ '\t'		# Rate [sat/(W*hour)]
	if MaxAuthorizedRateInterpolator is not None:
		DataString += RoundAndPadToString(MaxAuthorizedRateInterpolator(CurrentTime.timestamp()),4)	+ '\t'		# Max Authorized Rate [sat/(W*hour)]
	else:
		DataString += RoundAndPadToString(-1,4)								+ '\t'		# N/A for the seller

	DataString += RoundAndPadToString(Meter.EnergyCost,0)							+ '\t'		# EnergyCost
	DataString += RoundAndPadToString(Meter.EnergyPayments,0)						+ '\t'		# Total Payment Amount [sats]
	DataString += RoundAndPadToString(PaymentsReceived,0)							+ '\t'		# Total Number of Payments

	DataLogOutputFile.write(DataString+'\n')
	DataLogOutputFile.flush()		# skip this by changing the buffer mode of the open function?

	# where/when to close this file handle ?????








class UpdateVariables(Thread):
	def __init__(self,Meter,GUI,Mode,ZMQSocket=None):
		super(UpdateVariables, self).__init__()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		self.Meter=Meter
		self.GUI=GUI
		self.Mode=Mode
		self.ZMQSocket=ZMQSocket

		self.start()			# auto start on initialization

	def run(self):


		LoopCounter=0
		SleepTime=0.25
		ZMQPublishPeriod=10.0

		while True:
			LoopCounter+=1

			if self.GUI._stop_event.is_set():
				sys.exit()

			#pass values to the GUI
			self.GUI.Volts=self.Meter.Volts
			self.GUI.Amps=self.Meter.Amps
			self.GUI.Power=self.Meter.Power
			self.GUI.EnergyDelivered=self.Meter.EnergyDelivered
			self.GUI.RecentRate=self.Meter.RecentRate
			self.GUI.EnergyCost=self.Meter.EnergyCost
			self.GUI.EnergyPayments=self.Meter.EnergyPayments

			if self.Mode=='buyer':
				if self.Meter.ResponseReceived:
					self.GUI.BigStatus='Power ON'		#assume power is on if the meter is responding, but need to make this more exact!!!!!!!!!!!!!!!!

				elif self.GUI.BigStatus!='Power Expected':	#also need to make this smarter!!!!!!!!!!!!!!
					self.GUI.BigStatus='Power OFF'

				if LoopCounter>=ZMQPublishPeriod/SleepTime:
					LoopCounter=0
				elif LoopCounter==1:	#publish at the beginning of the period instead of the end.
					if self.Meter.RecentRate!=-1:
						# publish the rate via zmq so local devices can adjust their loads intelligently
						# continuously send because new clients can connect at any time and they won't know the current rate and don't want them to have to wait a while.
						PackTopicAndJSONAndSend(self.ZMQSocket,'Rate',self.Meter.RecentRate)		#note: using send_json even though just using a float because want to prepare for more complex messages
						TimeStampedPrint('Published a rate of '+RoundAndPadToString(self.Meter.RecentRate*100,0)+' sat/(100 W*hour) to ZMQ subscribers')
					else:
						# don't wait, send the rate once it's been initialized
						LoopCounter=0

			sleep(SleepTime)







