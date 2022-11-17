


###############################################################################
###############################################################################
# Copyright (c) 2022, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################




from inotify.adapters import Inotify
from pathlib import Path
from yaml import safe_load
from threading import Thread
from time import sleep
from hashlib import sha256
from helpers2 import TimeStampedPrint

TheDataFolder=str(Path.home())+'/.dc/'
RateFileName='RateFile.yaml'


class MonitorRateFile(Thread):

	def __init__(self,  *args, **kwargs):
		super(MonitorRateFile, self).__init__(*args, **kwargs)
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		# need to do this here so the entire script will crash if the file has a malformed file on initial startup and to make sure the script blocks until the first read completes.
		self.Data,self.Hash=self.ReadFiles()
		print('')
		TimeStampedPrint('   ~~~   INITIAL READ OF RATE FILE   ~~~')
		TimeStampedPrint(self.Data,prettyprint=True)
		print('')
		self.OldData=self.Data
		self.OldHash=self.Hash


	def ReadFiles(self):
		with open(TheDataFolder+RateFileName, 'r') as file:
			Data=safe_load(file)
		with open(TheDataFolder+RateFileName,"rb") as file:		#don't know if the "b" parameter matters to yaml and also don't know if file seaking could be messed up by this, so just re-read separately to check if the file changed.
			Hash=sha256(file.read()).hexdigest()			#reads the entire file in, but hopefully it's very small and won't take up too much memory.
		return Data,Hash


	def run(self):
		ConfigDirectoryWatcher = Inotify()
		ConfigDirectoryWatcher.add_watch(TheDataFolder)

		for (_, type_names, path, filename) in ConfigDirectoryWatcher.event_gen(yield_nones=False):
			if filename == RateFileName and 'IN_CLOSE_WRITE' in type_names:
				try:

					# self.Data is replaced with a new object instead of modifying the existing object.
					# all downstream references made to the old object will not be updated since they reference the old object.
					# however, deepcopy is used in GenerateCurrentSellOfferTerms and in the buyer's script when creating BuyOfferTerms because every time it is run,
					# RateFile.yaml has not yet changed, so there won't always be a new object created yet.
					self.Data,self.Hash=self.ReadFiles()

					if (self.OldData != self.Data):
						print('')
						TimeStampedPrint('   ~~~   RATE FILE CHANGED SINCE THE LAST SUCCESSFULL READ   ~~~')
						TimeStampedPrint(self.Data,prettyprint=True)
						print('')
					elif (self.OldHash == self.Hash):
						TimeStampedPrint('   ~~~   RATE FILE RE-WRITTEN BUT NOTHING CHANGED SINCE THE LAST SUCCESSFULL READ   ~~~')
					else:
						TimeStampedPrint('   ~~~   RATE FILE CHANGED SINCE THE LAST SUCCESSFULL READ BUT NO VALUES CHANGED (ONLY COMMENTS OR WHITESPACE CHANGED)   ~~~')

					# these don't need to be reset every time (they aren't actually changed every time), but it doesn't hurt and is slightly simpler.
					self.OldData=self.Data
					self.OldHash=self.Hash
				except:
					TimeStampedPrint('   ~~~   RATE FILE CHANGED SINCE THE LAST SUCCESSFULL READ BUT COULD NOT BE PROPERLY READ, KEEPING THE OLD RATE STRUCTURE  ~~~')


# if running standalone and not importing as a module, always print messages
if __name__ == "__main__":
	import helpers2
	helpers2.PrintWarningMessages=True


RateFile=MonitorRateFile()
RateFile.start()


# if running standalone and not importing as a module, keep running (since using the thread in daemon mode and the script won't wait for background threads before quitting) so that can test the file reloading process.
if __name__ == "__main__":
	while True:
		sleep(10)



