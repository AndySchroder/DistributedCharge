###############################################################################
###############################################################################
#Copyright (c) 2020, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################

"""This file is called helpers2.py and not helpers.py because my CycleCode project (http://andyschroder.com/CO2Cycle/SourceCode/)
already has a helpers.py file. Some functions were copied from helpers.py. This file, helpers2.py should eventually be moved
to it's own project and should have a few general functions that are found in helpers.py removed.
"""

from datetime import datetime


PrintWarningMessages=False	#set to True after importing the module to get warning messages




#define a more intelligent range and arange function because the default one is stupid for many uses and doesn't include the endpoint
def irange(start=None,stop=None,step=1):
	if (start is not None) and (stop is None) and (step == 1):
		#then user actually wants to just specify the stop
		stop=start
		start=1					#default to 1 instead of 0
	elif (start is None) and (stop is not None):
		start=1					#default to 1 instead of 0
	elif (start is None) and (stop is None):
		raise Exception('must specify a stop value')

	return range(start,stop+1,step)			#note, range's stop (actually stop-1) value is the maximum it can get to, but will be less if stop-1-step is not a multiple of step








def TimeStampedPrint(message):
	"""Print a message, prepending it with the date and time down to the millisecond."""
	if PrintWarningMessages:
		print(datetime.now().strftime('%Y.%m.%d--%H.%M.%S.%f')		+':   '+message)		#need to use datetime instead of time module to get fractions of a second


def RoundAndPadToString(Value,DecimalPlaces=3,LeftPad=None,PadCharacter=' '):
	"""Round a number to so many decimal places and zero pad if necessary and convert to a string."""
	LeftPadding=''
	if LeftPad is not None:
		#pad digits left of decimal place (LeftPad=2 for example converts "0.1" to " 0.1") up to this digit
		for digit in irange(2,LeftPad):				#skip the first digit, even if specified because it will always be there (will be a 0 if the value is less than 1) with the current formatting method used below
			if Value<10.0**(digit-1):
				LeftPadding+=str(PadCharacter)
				if digit in irange(4,LeftPad,3):	#every 3rd digit, starting with the fourth
					LeftPadding+=str(PadCharacter)	#be smart enough to also add padding for thousands separators
	return LeftPadding+'{1:,.{0}f}'.format(DecimalPlaces,Value)



def FormatTimeDeltaToPaddedString(delta):	#converts time delta to string in the zero madded format 00:00:00, (hours:minutes:seconds) . not sure what it does if the hours are greater than 99.
	hours, remainder = divmod(delta.total_seconds(), 3600)
	minutes, seconds = divmod(remainder, 60)
	return '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))






