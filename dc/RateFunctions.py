


###############################################################################
###############################################################################
# Copyright (c) 2024, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################




from numpy import linspace,cos,pi,trapz,sum,ndarray,concatenate,sort,unique,tile
from math import floor
from scipy.interpolate import interp1d
from datetime import datetime,timedelta
from time import time,sleep
from .ReadRates import RateFile
from threading import Thread
from copy import deepcopy





# TODO:
# - make rates also a function of power and allow buying or selling
# - define defaults if no rate file.






NumberOfPointsSineWavetimes=2**10
#NumberOfPointsSineWavetimes=25








def LinearRateInterpolator(StartTime,StopTime,RateValues):
	InterpolationTableTimes=linspace(StartTime,StopTime,len(RateValues))
	return InterpolationTableTimes,interp1d(InterpolationTableTimes,RateValues)


def SineWave(Min,Max,TimeShift,TimePeriod,SineWaveTimes):
	OrdinaryFrequency=1/TimePeriod
	AngularFrequency=2*pi*OrdinaryFrequency
	Phase=-TimeShift*AngularFrequency
	return ((Max-Min)/2)*(-cos(AngularFrequency*SineWaveTimes+Phase)+1)+Min


def GetCombinedSineWaves(SinusoidValues,SineWaveTimes):

	# need to use below to offset to beginning of the day and year (need to do because leap time will put things off if just relying on seconds since epoch).
	# could have a TimePeriod that is different from the nominal day/year instead, but just offsetting the start of the year works a little simpler.
	if type(SineWaveTimes) is ndarray:
		StartTimeTimeStamp=SineWaveTimes[0]
	elif type(SineWaveTimes) is float:
		StartTimeTimeStamp=SineWaveTimes
	else:
		raise Exception('not sure of the object type')
	StartTime=datetime.fromtimestamp(StartTimeTimeStamp)

	return	(
			SineWave(SinusoidValues['Day']['Min'],SinusoidValues['Day']['Max'],SinusoidValues['Day']['TimeShift']+datetime(StartTime.year,StartTime.month,StartTime.day).timestamp(),SinusoidValues['Day']['TimePeriod'],SineWaveTimes)
			+
			SineWave(SinusoidValues['Year']['Min'],SinusoidValues['Year']['Max'],SinusoidValues['Year']['TimeShift']+datetime(StartTime.year,1,1).timestamp(),SinusoidValues['Year']['TimePeriod'],SineWaveTimes)
		)


class CombinedSineWaves():
	def __init__(self,SinusoidValues):
		self.SinusoidValues=SinusoidValues
	def __call__(self,SineWaveTimes):
		return GetCombinedSineWaves(self.SinusoidValues,SineWaveTimes)


def ExtendedRateValues(OfferStartTime,OfferStopTime,BasicInterpolationTableValues):
	# need to create a new table to match the actual offer time period based on the allowable table so that it can be sent to the buyer and used in an interpolator function.
	# this will also extend to multiple days if the offer time period is multiple days. the current table input format is only good for one day.
	# also, since some error occurs when resampling, will use this by the seller to make sure that payment is coming in on time because need to match exactly with what the buyer is doing.
	OfferStartDateTime=datetime.fromtimestamp(OfferStartTime)
	StartOfTheDayOfferStart=datetime(OfferStartDateTime.year,OfferStartDateTime.month,OfferStartDateTime.day)
	StartOfTheDayOfferStartTime=StartOfTheDayOfferStart.timestamp()

	OfferStopDateTime=datetime.fromtimestamp(OfferStopTime)
	EndOfTheDayOfferStop=datetime(OfferStopDateTime.year,OfferStopDateTime.month,OfferStopDateTime.day)+timedelta(days=1)
	EndOfTheDayOfferStopTime=EndOfTheDayOfferStop.timestamp()

	NumberOfDaysInNewExtendedTable=(EndOfTheDayOfferStop-StartOfTheDayOfferStart).days

	_,ExtendedRateInterpolator=LinearRateInterpolator(StartOfTheDayOfferStartTime,EndOfTheDayOfferStopTime,tile(BasicInterpolationTableValues,NumberOfDaysInNewExtendedTable))

	# increase the resolution since being resampled and don't want to introduce error but limit to 4 points per minute.
	# could make it smarter and define the times for each point, then truncate the table and interpolate just the endpoints,
	# adding them only, but that is slightly more complicated.

	return ExtendedRateInterpolator(linspace(OfferStartTime,OfferStopTime,max(len(BasicInterpolationTableValues)*10,4*60*24)*NumberOfDaysInNewExtendedTable))


def SetInterpolator(Rate,OfferStartTime,OfferStopTime):
	"""
	Sets an interpolator function using the current Rate Type. Also, if an InterpolationTable is used, the BasicInterpolationTableValues are mapped to the actual time period of the offer if they have not already been.
	If the buyer is running this function on the sellers Rate, the seller's BasicInterpolationTableValues will already be mapped to the actual time period in InterpolationTableValues.
	"""

	# as noted elsewhere, Values for Types that are not selected by Type may be included by the seller, but the only ones that are in force in the agreement are what is selected by Type. also, value names starting with "Basic" are not
	# part of the agreement and can be considered reference only so the buyer can know what the seller has interpolated their rate profile from.

	if Rate['Type'] == 'Constant':
		# make a simple table of 2 points so can be generalized to use an interpolator. will waste time testing more points, but it makes everything generalized.
		# don't need to do anything for this one relative to the current day/year because it is always constant, so just make sure it is defined during the time window that the offer is for.
		InterpolationTableTimes,RateInterpolator=LinearRateInterpolator(OfferStartTime,OfferStopTime,[Rate['ConstantValue'],Rate['ConstantValue']])

	elif Rate['Type'] == 'InterpolationTable':

		if 'InterpolationTableValues' not in Rate:
			# this takes the time duration of the offer period and then makes sure the interpolation table is defined for those days
			# there is no change in the profile from day to day, so the interpolation table is copied for each day.
			Rate['InterpolationTableValues']=ExtendedRateValues(OfferStartTime,OfferStopTime,Rate['BasicInterpolationTableValues'])
		else:
			# InterpolationTableValues will already exist for the right time range when the buyer receive SellOfferTerms from the seller.
			pass

		InterpolationTableTimes,RateInterpolator=LinearRateInterpolator(OfferStartTime,OfferStopTime,Rate['InterpolationTableValues'])

	elif Rate['Type'] == 'Sinusoid':
		# combine daily and annual rate fluctuations together
		# shift the sine functions for leap year since a nominal year length is assumed, then also make the nominal minimum of the sine wave to be at the beginning of the year and midnight.
		# then apply a shift if defined in the Rate definition so that the minimum rate can be at a time other than midnight (such as March 1st and 0400)
		RateInterpolator=CombinedSineWaves(Rate['SinusoidValues'])				#not actually an interpolator (it's evaluating the function exactly), but the inputs/outputs are the same as the interpolators
		InterpolationTableTimes=linspace(OfferStartTime,OfferStopTime,NumberOfPointsSineWavetimes)		#hoping this is fine enough to not miss something.

	else:
		raise Exception("unknown Rate Type")


	return InterpolationTableTimes,RateInterpolator


def GenerateCurrentSellOfferTerms():
	# no variables are passed to this function because it uses the current rate required read from disk.
	# similiar to on the buyer's side, RateFile.yaml can be re-saved and re-read multiple times during the currently active sale period, but the changes will only take affect at this time.

	# need to do this because RateFile.yaml isn't always changed everytime a new sale period starts, so a new Data object isn't always created, so need to force creating a new one here since some things are added/changed and need it to be fresh.
	SellOfferTerms=deepcopy(RateFile.Data['SellOfferTerms'])

	Now=datetime.now()
	SellOfferTerms['OfferStartTime']=floor(Now.timestamp())		#round down so not dealing with fractional seconds in unix time.
	OfferStop=Now+timedelta(seconds=SellOfferTerms['Duration']['Time'])
	SellOfferTerms['OfferStopTime']=floor(OfferStop.timestamp())		#round down so not dealing with fractional seconds in unix time.
#any issues with OfferStopTime not matching (a gap, probably not an overlap) OfferStartTime for the next sale period?

	_,RequiredRateInterpolator=SetInterpolator(SellOfferTerms['Rate'],SellOfferTerms['OfferStartTime'],SellOfferTerms['OfferStopTime'])

	# as noted in the RateFile.yaml, extra Values may be sent, even if they are not selected by Type. might want to remove them from a privacy perspective here.
	# also, should the BasicInterpolationTableValues be removed too???? see also the buyer's script where InitialDepositMultiple is removed.

	return SellOfferTerms,RequiredRateInterpolator


def CheckRateAllowable(BuyOfferTerms,SellOfferTerms):
	"""
	Used by the buyer to check to see if their allowed rate profile matches what the seller requires.
	"""

	# combine all known points to test, then remove duplicates, and then sort (in case this is ever plotted so that it is not a mess).
	# points that are evaluated that are exactly the same as the input that goes into the InterpolationTable should return exact values.
	# note, some extra points are compared for constants, particularly when conservative values for sine wave maxima could be considered,
	# but it's more general and simpler this way. also, InterpolationTable maybe isn't even slower this way because still need to use
	# the max function to find the worse case extreme in the array to compare a constant to, and that might be the same amount of work
	# (or even less?) in the background as just comparing all points as is done here.
	CombinedInterpolationTableTimes=sort(unique(concatenate((SellOfferTerms['InterpolationTableTimes'],BuyOfferTerms['InterpolationTableTimes']))))

	if (BuyOfferTerms['RateInterpolator'](CombinedInterpolationTableTimes)-SellOfferTerms['RateInterpolator'](CombinedInterpolationTableTimes)).min()>=0:

#		print(CombinedInterpolationTableTimes)
#		print(BuyOfferTerms['RateInterpolator'](CombinedInterpolationTableTimes))
#		print(SellOfferTerms['RateInterpolator'](CombinedInterpolationTableTimes))

		return True
	else:
		return False






class MeterMonitor(Thread):
	def __init__(self, RawMeter,LocalMeterScalingFactor,ForceInitialRead=False):
		super(MeterMonitor, self).__init__()
		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.

		self.RawMeter=RawMeter
		self.LocalMeterScalingFactor=LocalMeterScalingFactor

		self.ResetMeter()		#since initalization also does everything that happens when reseting, just call this to do those steps.

		if ForceInitialRead:
			while True:
				if self.update():			#do one blocking update until a successful read before going to the background from the main thread.
					break

		self.start()			#auto start on initialization

	def ResetMeter(self):			#allow reseting after starting

		self.ResponseReceived=False

		self.EnergyDelivered=0
		self.OldMeasurement=-1

		self.Volts=-1
		self.Amps=-1
		self.Power=-1

		self.SellOfferTerms=None
		self.RequiredRateInterpolator=None
		self.RecentRate=-1
		self.EnergyCost=0
		self.EnergyPayments=0		#this is not used anywhere in this class, but just put it here because every time the meter is reset, also going to want to reset the energy payments

	def run(self):		# continuously update
		while True:
			self.update()

	def update(self):
		# separate this out into a separate function so can force one update before going into the background.

		self.ResponseReceived=self.RawMeter.request()		#what is the timeout for this command????

		if (self.ResponseReceived): # if the read succeeds, then get the data from the buffer

			CurrentRawMeterData = self.RawMeter.getReadBuffer()
			self.HistoricalEnergyDelivered=CurrentRawMeterData['kWh_Tot'][4]*self.LocalMeterScalingFactor
			self.Amps=CurrentRawMeterData['Amps_Ln_1'][4]
			self.Volts=CurrentRawMeterData['RMS_Volts_Ln_1'][4]
			self.Power=CurrentRawMeterData['RMS_Watts_Tot'][4]

			CurrentReadingTime=time()

			if (self.SellOfferTerms is not None) and (self.RequiredRateInterpolator is not None):	#if the rate structure has been defined

				self.RecentRate=self.RequiredRateInterpolator(CurrentReadingTime)			#for reference on the GUI only

				if self.OldMeasurement>-1:
					#the first reading has been taken, so now all readings can be used to check and see if there has been a change.

					NewEnergy=self.HistoricalEnergyDelivered-self.OldMeasurement

					if NewEnergy>0:

						# would prefer this to be larger than the resolution that the rate is defined at. since the time that is integrated over here is (assuming power levels aren't ultra low,
						# which they can't be because the meter uses some power) less than the total time the rate structure is defined, this is way more conservative
						# if the definition of the rate structure is low resolution, but there are fast changes where it's actually defined, 
						# doing integration over many points allows the discontinuities in CHANGE in RATE to be captured much better instead of being jumped over.

						try:
							NumberOfPoints=len(self.SellOfferTerms['Rate']['InterpolationTableValues'])
						except:
							NumberOfPoints=NumberOfPointsSineWavetimes

						self.EnergyCost+=trapz(self.RequiredRateInterpolator(linspace(self.LastNewReadingTime,CurrentReadingTime,NumberOfPoints)),dx=NewEnergy/(NumberOfPoints-1))
						self.EnergyDelivered+=NewEnergy
						self.LastNewReadingTime=CurrentReadingTime
						self.OldMeasurement=self.HistoricalEnergyDelivered
					else:
						#reading has not changed, so don't do anything.
						pass
				else:
						#first reading so need to reset somethings after the intial reading has been taken.
						self.LastNewReadingTime=CurrentReadingTime
						self.OldMeasurement=self.HistoricalEnergyDelivered

		return self.ResponseReceived







