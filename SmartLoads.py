


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

from pathlib import Path
from fabric import Connection
from time import sleep
from gpiozero import LED
from threading import Thread
from common import TheDataFolder,TheDataArchiveFolder,MakeFolderIfItDoesNotExist
from yaml import safe_load
from zmq import Context,SUB,SUBSCRIBE
from helpers2 import RoundAndPadToString,TimeStampedPrint,SetPrintWarningMessages,irange
from SocketHelpers import ReceiveAndUnPackTopicAndJSON
from datetime import datetime
from copy import copy
from numpy import asarray,abs


################################################################

SetPrintWarningMessages(True)


TimeStampedPrint('startup!')



# TODO : broadcast power level and then make Variable loads start to throttle back if power level is getting close to the maximum. this will require some feedback though because non-controlled loads are in the mix and will need to be continuously adjusted.



#######################################################################
# read in config file
#######################################################################

ConfigFileName='SmartLoads.yaml'

with open(TheDataFolder+ConfigFileName, 'r') as file:
	ConfigFile=safe_load(file)

# make some shorter reference names
LowLoadRate=ConfigFile['RateLimits']['LowLoadRate']
HighLoadRate=ConfigFile['RateLimits']['HighLoadRate']

#######################################################################





#######################################################################
# define classes and functions
#######################################################################

def FindNearestValue(TheArray, TheValue):				# inspired by https://stackoverflow.com/questions/2566412/find-nearest-value-in-numpy-array
	TheArray = asarray(TheArray)
	TheIndex = abs(TheArray-TheValue).argmin()		# need to use the absolute value of the difference to catch the closest value.
	return TheArray[TheIndex]


def ComputeAllowablePercentLoad(CurrentRate):
	CurrentRate=min(LowLoadRate, max(HighLoadRate, CurrentRate))	#constrain the range of the rate to within the limits of where the rate is defined. anything higher than the LowLoadRate will always come out to 0 with the following LoadFraction calculation and anything lower than HighLoadRate will always be at a load fraction of 1.0
	LoadFraction=1+(CurrentRate-HighLoadRate)/(HighLoadRate-LowLoadRate)
	return int(LoadFraction*100)


class LocalDiscreteLoad(Thread):
	"""
	Turn off discrete loads using the relays on Board A0 when the energy rate gets above the PowerOffRate which is determined from the load's priority.
	"""

	def __init__(self,Load):
		super(LocalDiscreteLoad, self).__init__()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		self.Load=Load
		self.LoadPriority=self.Load['LoadPriority']
		self.Contactor = LED(self.Load['GPIONumber'])

		self.start()			# auto start on initialization

	def run(self):

		TimeStampedPrint('Initializing '+self.Load['Description']+' to Off')
		self.Contactor.off()
		sleep(5)		# try to avoid a rapid restart if the current rate calls for this to actually be on and it was just on. putting this initialization here and not in __init__ so all loads can be doing this in parallel.

		while True:
			PowerOffRate=self.LoadPriority*(LowLoadRate-HighLoadRate)+HighLoadRate

			if CurrentRate>PowerOffRate:
				if self.Contactor.is_lit:
					TimeStampedPrint('CurrentRate='+RoundAndPadToString(CurrentRate*1000,0)+' sat/(kW*hour), Turning Off '+self.Load['Description'])
					self.Contactor.off()
			elif CurrentRate/PowerOffRate<(1.00-0.10):			#TODO: change this dead band to be relative to (LowLoadRate-HighLoadRate) or (CurrentRate-HighLoadRate)/(PowerOffRate-HighLoadRate)??????????????????
				if not self.Contactor.is_lit:
					TimeStampedPrint('CurrentRate='+RoundAndPadToString(CurrentRate*1000,0)+' sat/(kW*hour), Turning On '+self.Load['Description'])
					self.Contactor.on()
			else:
				# CurrentRate is less than the PowerOffRate but not yet below the 10% dead band.
				pass
			sleep(1)


class RemoteVariableLoad(Thread):
	"""
	Control a test variable load from 0% to 100% using stress-ng on a remote machine via SSH.
	"""

	def __init__(self,HostName,Port=None,NumberOfCPUsAvailable=0):
		super(RemoteVariableLoad, self).__init__()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		self.HostName=HostName
		self.Port=Port
		self.NumberOfCPUsAvailable=NumberOfCPUsAvailable

		self.start()			# auto start on initialization

	def run(self):
		OldPercentLoad=-1
		with Connection(self.HostName,port=self.Port) as RemoteServer:
			while True:

				self.PercentLoad=ComputeAllowablePercentLoad(CurrentRate)

				if OldPercentLoad!=self.PercentLoad:
					TimeStampedPrint('CurrentRate='+RoundAndPadToString(CurrentRate*1000,0)+' sat/(kW*hour), Setting PercentLoad to '+str(self.PercentLoad)+'% for '+self.HostName)
					OldPercentLoad=self.PercentLoad

				# use a 30 second timeout so that the response time for changing the load can be quicker, but this results in a short period of time every 30 seconds where not at 100% load while the script is restarting stress-ng.
				# NOTE: used to have a 10 second timeout but decided to increase to 30 seconds because of this concern.
				# also, stress-ng doesn't seem to die when disconnecting ssh with control-C, so that's another reason to have a short timeout so it will die a few moments later without manual intervention required.


					if self.NumberOfCPUsAvailable>0:
						NumberOfCPUsToUse=FindNearestValue(list(irange(0,self.NumberOfCPUsAvailable)),self.NumberOfCPUsAvailable*self.PercentLoad/100)
						TimeStampedPrint('Using '+str(NumberOfCPUsToUse)+'/'+str(self.NumberOfCPUsAvailable)+' CPUs @ 100% instead of '+str(self.NumberOfCPUsAvailable)+'/'+str(self.NumberOfCPUsAvailable)+' CPUs @ '+str(self.PercentLoad)+'% for '+self.HostName)

				if self.NumberOfCPUsAvailable>0:
					if NumberOfCPUsToUse>0:
						# discretely run a certain number of CPUs at 100% load. the more CPUs a machine has, the more this approximates a truely variable load. it seems that general CPUs (when using stress-ng
						# at least) have some fluctuation in the actual power consumptions and when doing it this way, it is a little bit more stable than using the --cpu-load option as is done further
						# below when the NumberOfCPUsToUse is not specified or is equal to 0.
						RemoteServer.run('stress-ng --cpu '+str(NumberOfCPUsToUse)+' --quiet --timeout 40')
					else:	# giving stress-ng a value of 0 will load all CPUs instead of 0, so need to manually catch this.
						sleep(1)
				else:
					# - use all CPUs and then tell stress-ng what percent CPU load to target for each CPU. it isn't perfectly accurate at achieving the requested load percentage, but it is a common command regardless of the number of
					# 	CPUs on the remote machine and also has more granularity than putting each CPU either at 100% or 0% load.

					RemoteServer.run('stress-ng --cpu 0 --quiet --cpu-load '+str(self.PercentLoad)+' --timeout 40')


#######################################################################





#######################################################################
# connect to zmq server and then get an initial rate
#######################################################################

# note, this connection is not secure, but it's assumed okay for now because it should only be used on a local network

socket = Context().socket(SUB)
socket.connect('tcp://'+ConfigFile['RateServer']['HostName']+':5555')
socket.setsockopt(SUBSCRIBE, b'Rate')		#seems to need to be "bytes" even though sending the topic as a string because send_string must convert it to binary


#get an initial rate before allowing any of the background load control threads to start
TimeStampedPrint('Waiting for the first rate value to be received.')
_,CurrentRate=ReceiveAndUnPackTopicAndJSON(socket)

#######################################################################






#######################################################################
# start up load control background threads
#######################################################################


# start up background threads for different discrete loads that are controlled via a local relay and turn those loads off and on based on changes in energy rates
LocalDiscreteLoads=[]
for Load in ConfigFile['LocalDiscreteLoadDetails']:
	LocalDiscreteLoads.append(LocalDiscreteLoad(Load))



# start up background threads for each remote server that will vary a test load based on changes in energy rates
RemoteVariableLoads=[]
for Load in ConfigFile['RemoteVariableLoadDetails']:
	if 'Port' in Load:
		Port=Load['Port']
	else:
		Port=None

	if 'NumberOfCPUsAvailable' in Load:
		NumberOfCPUsAvailable=Load['NumberOfCPUsAvailable']
	else:
		NumberOfCPUsAvailable=0

	RemoteVariableLoads.append(RemoteVariableLoad(Load['HostName'],Port,NumberOfCPUsAvailable))

#######################################################################







TheDiscreteSmartLoadDataLogFolder=TheDataArchiveFolder+'/DiscreteSmartLoadDataLog/'
TimeStampedPrint('DiscreteSmartLoadDataLogFolder set to '+TheDiscreteSmartLoadDataLogFolder)
MakeFolderIfItDoesNotExist(TheDiscreteSmartLoadDataLogFolder)

TheVariableSmartLoadDataLogFolder=TheDataArchiveFolder+'/VariableSmartLoadDataLog/'
TimeStampedPrint('VariableSmartLoadDataLogFolder set to '+TheVariableSmartLoadDataLogFolder)
MakeFolderIfItDoesNotExist(TheVariableSmartLoadDataLogFolder)

# open the output files --- need to fix this so that it re-opens a new file every day, but right now, it just sticks with the file created during the time it was started up.
DiscreteSmartLoadDataLogOutputFile = open(TheDiscreteSmartLoadDataLogFolder+'DiscreteSmartLoadDataLog-'+datetime.now().strftime('%Y.%m.%d--%H.%M.%S.%f')+'.txt', "a")
VariableSmartLoadDataLogOutputFile = open(TheVariableSmartLoadDataLogFolder+'VariableSmartLoadDataLog-'+datetime.now().strftime('%Y.%m.%d--%H.%M.%S.%f')+'.txt', "a")






#######################################################################
# monitor zmq for rate changes
#######################################################################

OldRate=-1		# ignore the rate just received above because want it to still print out on the first iteration of this loop (which will be the second rate received so it will be a little delayed printing from the first status messages from all the load controllers).
while True:

	_,CurrentRate=ReceiveAndUnPackTopicAndJSON(socket)	# TODO: more sanity checks on the received rate (like is it less than 0 or ultra big or anything weird).

	if round(CurrentRate,2)!=round(OldRate,2):		#don't notify of small changes even though the rest of the script considers them (except ComputeAllowablePercentLoad)
		TimeStampedPrint('New rate of '+RoundAndPadToString(CurrentRate*1000,0)+' sat/(kW*hour) received')

	OldRate=CurrentRate


	## write data to a TAB delimited text file for data analysis ##
	# date_time is redundant with unix_time (but make the log file easier to read when just casually looking at it) since can use datetime.datetime.fromtimestamp(unix_time) to easily get year,month,day,hour,minute,second for doing statistics on.
	# CurrentRate is also provided for reference in both DiscreteSmartLoadDataLogOutputFile and VariableSmartLoadDataLogOutputFile to make it easier to casually observe,
	# but it is also shown (at nearly (but not exactly) the same time) in DataLogOutputFile from the grid-buyer.py and grid-seller.py scripts.

	# want all time references to be exactly the same, so use this moment as the reference.
	CurrentTime=datetime.now()

	LineHeaderDataString = ''
	LineHeaderDataString += RoundAndPadToString(CurrentTime.timestamp(),4,ShowThousandsSeparator=False)			+ '\t'		# unix_time
	LineHeaderDataString += CurrentTime.strftime('%Y.%m.%d--%H.%M.%S.%f')							+ '\t'		# date_time
	LineHeaderDataString += RoundAndPadToString(CurrentRate,4)								+ '\t'		# Rate [sat/(W*hour)]


	DiscreteSmartLoadDataString=copy(LineHeaderDataString)
	for LocalDiscreteLoadInstance in LocalDiscreteLoads:
		DiscreteSmartLoadDataString += RoundAndPadToString(LocalDiscreteLoadInstance.Contactor.is_lit*100.,2)		+ '\t'		# percent load (which is only 0% or 100% for a discrete load)

	VariableSmartLoadDataString=copy(LineHeaderDataString)
	for RemoteVariableLoadInstance in RemoteVariableLoads:
		VariableSmartLoadDataString += RoundAndPadToString(RemoteVariableLoadInstance.PercentLoad,2)			+ '\t'		# percent load


	DiscreteSmartLoadDataLogOutputFile.write(DiscreteSmartLoadDataString+'\n')
	DiscreteSmartLoadDataLogOutputFile.flush()		# skip this by changing the buffer mode of the open function?

	VariableSmartLoadDataLogOutputFile.write(VariableSmartLoadDataString+'\n')
	VariableSmartLoadDataLogOutputFile.flush()		# skip this by changing the buffer mode of the open function?

	# where/when to close the file handles ?????



#######################################################################






