


###############################################################################
###############################################################################
# Copyright (c) 2025, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################


# first must import config variables from the parent module
from . import mode, TheConfigFile, TheDataFolder, LNDhost

from pathlib import Path
from os import makedirs,environ
from os.path import isfile,isdir
from helpers2 import RoundAndPadToString,FullDateTimeString,FormatTimeDeltaToPaddedString,SetPrintWarningMessages
from textwrap import indent,dedent
from threading import Thread
from .SocketHelpers import PackTopicAndJSONAndSend
from .GUI import GUIClass					# might want to rename this module since GUI is used below for the actual GUI object?
from dc.m3 import m3, getCANvalue
from time import sleep
from datetime import datetime
from pydbus import SystemBus
from lndgrpc import LNDClient
from argparse import ArgumentParser, RawDescriptionHelpFormatter

from yaml import safe_load
import can, isotp


from smtplib import SMTP
from socket import gethostname
from getpass import getuser
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate,make_msgid







################################
# need to clean this up and make a smarter way to detect if running on raspi or not

try:
	from gpiozero import LED               # https://gpiozero.readthedocs.io/
	import mcp3008
except:
	pass

########################################################################################








################################################################
# cleanly catch shutdown signals
################################################################

from signal import signal, SIGABRT, SIGILL, SIGINT, SIGSEGV, SIGTERM

# catch kill signals so can cleanly shut down. this is critical to properly restore state of digital outputs to turn everything off, write files back to disk, properly release network sockets, etc..
def clean(*args):
	sys.exit(0)

def CatchKill():
	# warning, does not catch SIGKILL. hopefully whatever is launching the script also does not
	# die and this script is restarted soon if SIGKILL'ed (and this script dies without executing
	# the "finally" clause below doing a proper shutdown) and does a proper reset on re-startup of
	# digital outputs to a safe default since digital outputs remember their state when
	# SIGKILL'ed (don't want the script to die and leave a digital output powered on that
	# powers a relay that powers a motor for example, but instead want the script to restart
	# and quickly return that relay to its nominal off position).
	# note, SIGKILL of the launcher script will not kill this script though, it will detach and stay running.
	for sig in (SIGABRT, SIGILL, SIGINT, SIGSEGV, SIGTERM):
		signal(sig, clean)

CatchKill()















################################################################
# define party mappings
################################################################

PartyMappings = {
			'car': 'Buyer',
			'wall': 'Seller',
			'grid-buyer': 'Buyer',
			'grid-seller': 'Seller',
			'lnd-grpc-test-Buyer': 'Buyer',
			'lnd-grpc-test-Seller': 'Seller',
		}


################################################################


def EnvironmentPopulated(VariableName):
	return ((VariableName in environ) and (environ.get(VariableName) != None) and (environ.get(VariableName) != ''))

def MakeFolderIfItDoesNotExist(Folder):
	if not isdir(Folder):
		makedirs(Folder)
		return True
	else:
		return False


################################################################
# adjust directory paths from the defaults if they have been defined by an environmental variable if not passed on the command line (only in lnd-grpc-test for now) and create TheDataFolder if it does not exist
################################################################

if TheDataFolder == str(Path.home())+'/.dc/' and EnvironmentPopulated('DC_DATADIR'):
	TheDataFolder=environ.get('DC_DATADIR')
MadeNewDataFolder=MakeFolderIfItDoesNotExist(TheDataFolder)


if EnvironmentPopulated('DC_DATAARCHIVEDIR'):
	TheDataArchiveFolder=Path(environ.get('DC_DATAARCHIVEDIR'))
else:
	TheDataArchiveFolder=Path(TheDataFolder) / 'DataArchive'

################################################################























################################################################
# setup logging
################################################################

import sys,logging
from datetime import datetime

class PreciseTimeFormatterWithColorizedLevel(logging.Formatter):

	COLOR_CODES = {
		logging.CRITICAL: "\033[1;35m", # bright/bold magenta
		logging.ERROR:    "\033[1;31m", # bright/bold red
		logging.WARNING:  "\033[1;33m", # bright/bold yellow
		logging.INFO:     "\033[0;37m", # white / light gray
		logging.DEBUG:    "\033[1;30m"  # bright/bold black / dark gray
	}

	RESET_CODE = "\033[0m"

	converter=datetime.fromtimestamp			# need to use datetime because time.strftime doesn't do microseconds, which is what is used in https://github.com/python/cpython/blob/3.11/Lib/logging/__init__.py
	def formatTime(self, record, datefmt):
		if datefmt is None:                     # logging.Formatter (?) seems to set it as None if not defined, so can't just define the default in the definition of formatTime
			datefmt='%Y.%m.%d--%H.%M.%S.%f'
			ct = self.converter(record.created)
		return ct.strftime(datefmt)

	def __init__(self, color, *args, **kwargs):
		super(PreciseTimeFormatterWithColorizedLevel, self).__init__(*args, **kwargs)
		self.color = color

	def format(self, record, *args, **kwargs):
		if (self.color == True):

			record.TIMEDATECOLOR = "\033[1;37;40m"		# simple example https://www.kaggle.com/discussions/general/273188
			record.FUNCTIONNAMECOLOR = "\033[1;37;44m"

			if (record.levelno in self.COLOR_CODES):
				record.color_on  = self.COLOR_CODES[record.levelno]
				record.color_off = self.RESET_CODE
		else:
			record.color_on  = ""
			record.color_off = ""
			record.TIMEDATECOLOR = ""
			record.FUNCTIONNAMECOLOR = ""

		return super(PreciseTimeFormatterWithColorizedLevel, self).format(record, *args, **kwargs)




#console_log_level="info"
console_log_level="debug"
logfile_log_level="debug"

FormatStringTemplate='%(TIMEDATECOLOR)s%(asctime)s%(color_off)s [%(color_on)s%(levelname)8s%(color_off)s, %(FUNCTIONNAMECOLOR)s%(funcName)8.8s%(color_off)s]:   %(message)s'

# use the root logger rather than this module's logger so the settings defined in this module are applied to the root and other
# (sibling) modules at the same level as this module also inherit the settings applied here.
# see also: https://stackoverflow.com/questions/50714316/how-to-use-logging-getlogger-name-in-multiple-modules
logger = logging.getLogger()

logger.setLevel(logging.DEBUG)

console = logging.StreamHandler(sys.stdout)
console.setLevel(console_log_level.upper())
ColorizeConsole=sys.stdout.isatty()				# if directed to a tty colorize, otherwise don't (so won't get escape sequences in systemd logs for example)
console.setFormatter(PreciseTimeFormatterWithColorizedLevel(fmt=FormatStringTemplate, color=ColorizeConsole))


logfile = logging.FileHandler(TheDataFolder+"debug.log")
logfile.setLevel(logfile_log_level.upper()) # only accepts uppercase level names
logfile.setFormatter(PreciseTimeFormatterWithColorizedLevel(fmt=FormatStringTemplate, color=False))

logger.addHandler(console)
logger.addHandler(logfile)


# needs to be after creating TheDataFolder so it has a place to write to but not waiting until reading TheConfigFile, because always want to write this, regardless of the value of DebugLevel
logger.info('--------------------- startup ! ---------------------')

################################################################






















################################################################
# general functions
################################################################


class LogData:

	def __init__(self,Meter,GUI):

		# assign variables passed on initialization to the class
		self.Meter=Meter
		self.GUI=GUI

		# prepare directories
		if not TheDataLogFolder.is_dir():
			logger.info(str(TheDataLogFolder)+' does not exist, so creating it and any needed parents')
			TheDataLogFolder.mkdir(parents=True)

		# open the file handle
		self.DataLogFile='DataLog-'+datetime.now().strftime('%Y.%m.%d--%H.%M.%S.%f')+'.txt'		# give a new filename that has the time in which the file was created (which is approximately when the session was started (within some milliseconds)).
		logger.debug('opening DataLogFileHandle for '+self.DataLogFile)
		self.DataLogFileHandle = (TheDataLogFolder / self.DataLogFile).open("w", buffering=1)		# open for writing and line buffer writing. don't think this flushes OS filesystem buffers too. might want to add that down below after each write?????

		# now that the file handle has been created, write the column headers on the first line
		ColumnHeaders  = ''
		ColumnHeaders += 'UnixTime'				+ '\t'
		ColumnHeaders += 'DateTime'				+ '\t'
		ColumnHeaders += 'SessionTime'				+ '\t'
		ColumnHeaders += 'SalePeriodTimeRemaining[sec]'		+ '\t'
		ColumnHeaders += 'SalePeriodNumber'			+ '\t'
		ColumnHeaders += 'Power[W]'				+ '\t'
		ColumnHeaders += 'Volts'				+ '\t'
		ColumnHeaders += 'Amps'					+ '\t'
		ColumnHeaders += 'EnergyDelivered[Wh]'			+ '\t'
		ColumnHeaders += 'Rate[sat/Wh]'				+ '\t'
		ColumnHeaders += 'MaxAuthorizedRate[sat/Wh]'		+ '\t'
		ColumnHeaders += 'EnergyCost[sat]'			+ '\t'
		ColumnHeaders += 'TotalPaymentAmount[sat]'		+ '\t'
		ColumnHeaders += 'TotalNumberOfPayments'		+ '\t'
		ColumnHeaders += '\n'
		self.DataLogFileHandle.write(ColumnHeaders)




	def LogTabularDataAndMessages(self):

		# want all time references to be exactly the same, so use this moment as the reference.
		CurrentTime=datetime.now()

		## write data to the console/log file for live monitoring##

		StatusMessage  = ''
		StatusMessage += 'Power: '+RoundAndPadToString(self.Meter.Power,0)+' W,   '
		StatusMessage += 'Volts: '+RoundAndPadToString(self.Meter.Volts,2)+',   '
		StatusMessage += 'Amps: '+RoundAndPadToString(self.Meter.Amps,2)
		StatusMessage += '\n'
		StatusMessage += 'Energy Received: '+ RoundAndPadToString(self.Meter.EnergyDelivered,0)+' W*hours,   '
		StatusMessage += 'Energy Cost: '+RoundAndPadToString(self.Meter.EnergyCost,0)+' sats,   '
		StatusMessage += 'Credit Remaining: ' + RoundAndPadToString(self.Meter.EnergyPayments-self.Meter.EnergyCost,0)+' sats'
		StatusMessage += '\n'
		StatusMessage += 'Required Rate: '+RoundAndPadToString(self.Meter.RecentRate*1000,0)+' sat/(kW*hour),   '
		if self.Meter.BuyOfferTerms['RateInterpolator'] is not None:
			StatusMessage += 'Max Authorized Rate: '+RoundAndPadToString(self.Meter.BuyOfferTerms['RateInterpolator'](CurrentTime.timestamp())*1000,0)+' sat/(kW*hour)'
		StatusMessage += '\n'
		StatusMessage += 'Sale Period: ['
		StatusMessage += FullDateTimeString(self.Meter.SellOfferTerms['OfferStartTime'])+' <~~> '
		StatusMessage += FullDateTimeString(self.Meter.SellOfferTerms['OfferStopTime'])+'],  '
		StatusMessage += 'Remaining:'+FormatTimeDeltaToPaddedString(self.Meter.SellOfferTerms['OfferStopTime']-CurrentTime.timestamp())+',  '
		StatusMessage += 'Period #:'+RoundAndPadToString(self.Meter.SalePeriods,0)
		StatusMessage += '\n'
		StatusMessage += 'Total Payments: '+RoundAndPadToString(self.Meter.EnergyPayments,0)+' sats,   '
		StatusMessage += 'Number Payments: '+RoundAndPadToString(self.Meter.NumberOfPaymentsReceived,0)+',   '
		StatusMessage += 'Session Time: '+self.GUI.ChargeTimeText
		StatusMessage  = '\n' + indent(StatusMessage,' '*30)	#*35)
		StatusMessage += '\n'
		logger.info(StatusMessage)
#TODO: add some of this information to the GUI that is not already there



		## write data to a TAB delimited text file for data analysis ##

		# date_time is redundant with unix_time (but make the log file easier to read when just casually looking at it) since can use datetime.datetime.fromtimestamp(unix_time) to easily get year,month,day,hour,minute,second for doing statistics on.
		# Session Time is also provided for reference, but can be calculated by subtracting each row's unix_time from the first row's unix_time.

		DataString = ''
		DataString += RoundAndPadToString(CurrentTime.timestamp(),4,ShowThousandsSeparator=False)		+ '\t'		# unix_time
		DataString += CurrentTime.strftime('%Y.%m.%d--%H.%M.%S.%f')						+ '\t'		# date_time
		DataString += self.GUI.ChargeTimeText									+ '\t'		# Session Time
		DataString += RoundAndPadToString(self.Meter.SellOfferTerms['OfferStopTime']-CurrentTime.timestamp(),4)		+ '\t'		# Sale Period Time Remaining (seconds with thousands separator)
		DataString += RoundAndPadToString(self.Meter.SalePeriods,0)							+ '\t'		# Sale Period Number

		DataString += RoundAndPadToString(self.Meter.Power,5)							+ '\t'		# Power [W]
		DataString += RoundAndPadToString(self.Meter.Volts,3)							+ '\t'		# Volts
		DataString += RoundAndPadToString(self.Meter.Amps,3)								+ '\t'		# Amps
		DataString += RoundAndPadToString(self.Meter.EnergyDelivered,2)						+ '\t'		# EnergyDelivered [W*hours]

		DataString += RoundAndPadToString(self.Meter.RecentRate,4)							+ '\t'		# Rate [sat/(W*hour)]
		if self.Meter.BuyOfferTerms['RateInterpolator'] is not None:
			DataString += RoundAndPadToString(self.Meter.BuyOfferTerms['RateInterpolator'](CurrentTime.timestamp()),4)	+ '\t'		# Max Authorized Rate [sat/(W*hour)]
		else:
			DataString += RoundAndPadToString(-1,4)								+ '\t'		# N/A for the seller

		DataString += RoundAndPadToString(self.Meter.EnergyCost,0)							+ '\t'		# EnergyCost [sat]
		DataString += RoundAndPadToString(self.Meter.EnergyPayments,0)						+ '\t'		# Total Payment Amount [sat]
		DataString += RoundAndPadToString(self.Meter.NumberOfPaymentsReceived,0)							+ '\t'		# Total Number of Payments

		self.DataLogFileHandle.write(DataString+'\n')


	def close(self):
		logger.debug('closing DataLogFileHandle for '+self.DataLogFile)
		self.DataLogFileHandle.close()

	def __del__(self):
		logger.debug('LogData instance being garbage collected')
		self.close()		# try to close in case it is not already closed (running .close() a second time doesn't hurt and doesn't cause an error either).





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
						logger.info('Published a rate of '+RoundAndPadToString(self.Meter.RecentRate*1000,0)+' sat/(kW*hour) to ZMQ subscribers')
					else:
						# don't wait, send the rate once it's been initialized
						LoopCounter=0

			sleep(SleepTime)







class SMTPNotification(Thread):

	def __init__(self,subject,text):
		super(SMTPNotification, self).__init__()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		self.subject=subject
		self.text=text

		self.start()			# auto start on initialization


	def run(self):

		# if configured, then send e-mail
		try:
			logger.debug('sending e-mail notification')

			if 'sender' in ConfigFile['Notifications']['SMTP'] and ConfigFile['Notifications']['SMTP']['sender'] is not None:
				send_from=ConfigFile['Notifications']['SMTP']['sender']
			else:
				send_from=getuser()+'@'+gethostname()

			assert isinstance(ConfigFile['Notifications']['SMTP']['recipients'], list)

			send_date=None
			msg = MIMEMultipart()
			msg['From'] = send_from
			msg['To'] = COMMASPACE.join(ConfigFile['Notifications']['SMTP']['recipients'])
			if send_date is None:
				send_date = formatdate(localtime=True)
			msg['Date'] = send_date
			msg['Subject'] = self.subject
			msg['Message-ID']=make_msgid()          #add this because google email servers decided they want it for some reason as of August, 2022.

			msg.attach(MIMEText(self.text))

			while True:
				try:
					smtp = SMTP(ConfigFile['Notifications']['SMTP']['server'],ConfigFile['Notifications']['SMTP']['port'])

					#hopefully this actually starts a secure connection like it is supposed to do.
					smtp.starttls()
					smtp.ehlo()

					smtp.login(ConfigFile['Notifications']['SMTP']['username'], ConfigFile['Notifications']['SMTP']['password'])
					smtp.sendmail(send_from, ConfigFile['Notifications']['SMTP']['recipients'], msg.as_string())
					smtp.close()

					logger.debug('sent e-mail notification')

					break
				except:
					logger.exception('error sending e-mail. waiting 5 seconds and trying again.')
					sleep(5)

		except:
			logger.debug('e-mail not configured properly, not sending e-mail notification')





def LogAndSmallStatusUpdate(Message,GUI):
	GUI.SmallStatus=Message
	logger.debug(Message)


def WaitForTimeSync(GUI):
	GUI.BigStatus='Clock Not Set'
	LogAndSmallStatusUpdate('Waiting for clock to be synchronized with NTP server.',GUI)

	while not SystemBus().get(".timedate1").NTPSynchronized:
		sleep(0.1)

	GUI.BigStatus='Clock Set'
	LogAndSmallStatusUpdate('Clock is now synchronized with NTP server.',GUI)

















if	(
		(
			(
				mode is not None and 'lnd-grpc-test' in mode
				and
				LNDhost is None		# when running lnd-grpc-test, nothing else is needed from TheConfigFile if LNDhost is passed
			)
			or
			(mode is not None and 'lnd-grpc-test' not in mode)		# still want to read config if dc.LNDhost is not None because need other things in there
		)
		and
		(
			mode in PartyMappings
			and
			Path(TheDataFolder+TheConfigFile).is_file()
		)
	):

	################################################################
	# import values from config file
	################################################################

	with open(TheDataFolder+TheConfigFile, 'r') as file:
		ConfigFile=safe_load(file)


	# change the default value for the log file (standard output remains at INFO)
	logfile.setLevel(ConfigFile[PartyMappings[mode]]['DebugLevel'].upper())

	################################################################

	ConfigLoaded = True
	logger.info('configuration loaded')

else:
	ConfigLoaded = False
	logger.info('no configuration loaded')



################################################################
# set and create directories
################################################################


# needs to be after loading configuration since setLevel() needs to know the value of DebugLevel
logger.info('DataFolder set to '+TheDataFolder)
if MadeNewDataFolder:
	# couldn't write this until there was a place to write it to, so had to remember and then write when it was possible and setLevel() is already run.
	logger.info(TheDataFolder+' did not exist, so created it!')


logger.info('DataArchiveFolder set to '+str(TheDataArchiveFolder))		# not creating this folder here. instead, anything that needs to write here is responsible for making sure it exists.

TheDataLogFolder=TheDataArchiveFolder / 'DataLogs'
logger.info('TheDataLogFolder set to '+str(TheDataLogFolder))		# not creating this folder here. instead, anything that needs to write here is responsible for making sure it exists.



################################################################










logger.info('mode: '+str(mode))




if mode in PartyMappings:
	logger.info('Party: '+PartyMappings[mode])

	if not ConfigLoaded and LNDhost is None:
		raise Exception(TheDataFolder+TheConfigFile+' not loaded and no LNDhost defined')


	################################################################
	#initialize the LND RPC
	################################################################

	if LNDhost is None:		# get the value from the config file if not explicitly set.
		LNDhost=ConfigFile[PartyMappings[mode]]['LNDhost']

	lnd = LNDClient(LNDhost)
	logger.info('connected to lnd node '+lnd.host+' at block height '+str(lnd.get_best_block().block_height))

	################################################################


	if not ConfigLoaded and 'lnd-grpc-test' not in mode:
		raise Exception(TheDataFolder+TheConfigFile+' not loaded and required')


	if mode == 'car' or mode == 'wall':

		################################################################
		# initialize GPIO
		################################################################

		SWCAN_Relay = LED(16)

		#should be off on boot, but just make sure it is off on startup in case the script crashed/killed with it on and is being restarted without rebooting.
		SWCAN_Relay.off()

		################################################################



		################################################################
		# initialize the SWCAN bus
		################################################################

		can_Message = can.Message		# make it so this can be imported by other things importing SWCAN and TWCAN because don't think could import can.Message (but maybe should test it!!!!!!!)

		SWCAN = can.interface.Bus(channel=ConfigFile[PartyMappings[mode]]['SWCANname'], bustype='socketcan',can_filters=[	#only pickup IDs of interest so don't waste time processing tons of unused data
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

		RXID = {}
		RXID['wall']	= 1996
		RXID['car']	= 1997

		TXID = {	# rxid of wall is txid of car, and txid of wall is rxid of the car
				'wall' : RXID['car'],
				'car'  : RXID['wall']
			}

		#CAN ISOTP is a higher level protocol used to transfer larger amounts of data than the base CAN allows
		#this creates its own separate socket to the CAN bus on the same single wire can interface from the
		#other standard can messaging that occurs in this script

		SWCAN_ISOTP = isotp.socket(timeout=0.1)
		SWCAN_ISOTP.set_fc_opts(stmin=25, bs=10)		#see https://can-isotp.readthedocs.io/en/latest/isotp/socket.html#socket.set_fc_opts . note: car used to use stmin=5 but don't remember why
		SWCAN_ISOTP.bind(ConfigFile[PartyMappings[mode]]['SWCANname'], isotp.Address(rxid=RXID[mode], txid=TXID[mode]))



		################################################################







	if mode == 'car':

		################################################################
		# initialize the CAN bus
		################################################################
		TWCAN = can.interface.Bus(channel=ConfigFile[PartyMappings[mode]]['TWCANname'], bustype='socketcan',can_filters=[
												{"can_id": 0x3d2, "can_mask": 0x7ff, "extended": False},	#battery charge/discharge
												{"can_id": 1990, "can_mask": 0x7ff, "extended": False},
												{"can_id": m3.get_message_by_name('ID21DCP_evseStatus').frame_id, "can_mask": 0x7ff, "extended": False},
												{"can_id": m3.get_message_by_name('ID31CCC_chgStatus').frame_id, "can_mask": 0x7ff, "extended": False},
												{"can_id": m3.get_message_by_name('ID32CCC_logData').frame_id, "can_mask": 0x7ff, "extended": False},
												{"can_id": m3.get_message_by_name('ID292BMS_SOC').frame_id, "can_mask": 0x7ff, "extended": False},
												])
		################################################################

	elif mode == 'wall':

		################################################################
		# initialize the mcp3008
		################################################################

		Vref=3.3
		adc = mcp3008.MCP3008(1,max_speed_hz=int(976000/15))

		def PilotAnalogVoltage():
			return adc.read([mcp3008.CH1],Vref)[0]*7.6-12-.22

		def ProximityAnalogVoltage():
			return adc.read([mcp3008.CH0],Vref)[0]*3.2/2.2



		################################################################








if mode is not None and 'lnd-grpc-test' not in mode:

	################################################################
	# parse the command line
	################################################################

	parser = ArgumentParser(
										formatter_class=RawDescriptionHelpFormatter,
										epilog=dedent('''
										additional information:
											 Exit :                Control+C or Escape
											 Toggle Fullscreen :   f or double click
										''')
									)
	parser.add_argument('--fullscreen', action='store_true',help="Run full screen (default: %(default)s).")
	parser.add_argument('--maximized', action='store_true',help="Start maximized (default: %(default)s).")
	parser.add_argument('--geometry',type=str,help="Start with specific window size and position, i.e. 800x480+100+50 .")
	arguments=parser.parse_args()



	################################################################

	# launch the GUI
	GUI=GUIClass(arguments)		#create the thread
	GUI.start()			#starts .run() (and maybe some other stuff?)

	WaitForTimeSync(GUI)

	# uncomment to add a pause if doing a screen record and need time to organize windows to the right size before anything else gets printed to standard output.
	#sleep(120)




