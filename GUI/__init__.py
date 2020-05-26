###############################################################################
###############################################################################
#Copyright (c) 2020, Andy Schroder
#See the file README.md for licensing information.
###############################################################################
###############################################################################




from time import sleep
from datetime import datetime,timedelta

import threading,helpers2,os

from PIL import ImageTk, Image
from tkinter import Tk,StringVar,Label,CENTER,Frame,LEFT


FormatTimeDeltaToPaddedString=helpers2.FormatTimeDeltaToPaddedString
RoundAndPadToString=helpers2.RoundAndPadToString




class GUIClass(threading.Thread):
	#this class operates in another thread in daemon mode, and will shutdown if the .stop() method is used.
	#see also notes about stoppable threads in the ReceiveInvoices class


	def __init__(self,  *args, **kwargs):
		super(GUIClass, self).__init__(*args, **kwargs)
		self._stop_event = threading.Event()

		self.daemon=True		# using daemon mode so control-C will stop the script and the threads.


		#initialize variables, trying to make them match the main scripts initial values, although don't know if it really matters
		self.Volts=0
		self.Amps=0
		self.BigStatus=''
		self.SmallStatus=''
		self.EnergyDelivered=0
		self.EnergyPaidFor=0
		self.CurrentRate=0
		self.RequiredPaymentAmount=0
		self.ChargeStartTime=-1
		self.Proximity=0
		self.MaxAmps=0

	def stop(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

	def run(self):


		GUI=Tk()

		BigStatusTextv = StringVar()
		SmallStatusTextv = StringVar()


		def close(event):
			self._stop_event.set()
		GUI.bind('<Escape>', close)		#doesn't work in full screen, not sure why, but Control+C works then, so it's good enough for now


		#see note above about how Control+C is the only way to quit when in full screen mode.
		#warning, Alt+Tab does not work right either in full screen mode, so if you Alt+Tab and then Control+C,
		#you won't be actually doing Control+C to the right window.
		if True:
			GUI.geometry('1900x1025+0+0')
		else:
			#full screen
			GUI.overrideredirect(True)
			GUI.geometry('{0}x{1}+0+0'.format(GUI.winfo_screenwidth(),GUI.winfo_screenheight()))


		GUI.configure(background='white')#'green')

		TopFrame = Frame(GUI,background='white')#'orange')
		TopFrame.pack(side="top",anchor='n',fill='x')

		MiddleFrame = Frame(GUI,background='white')
		MiddleFrame.pack(side="top",anchor='s',fill='both',expand=True,pady=(30,30))

		BottomFrame = Frame(GUI,background='white')#'grey')
		BottomFrame.pack(side="bottom",anchor='s',fill='x')


		LeftFrame = Frame(TopFrame,background='white')#'black')
		LeftFrame.pack(side="left")

		RightFrame = Frame(TopFrame,background='white')#'blue')
		RightFrame.pack(side="right",fill='x', expand=True)

		ClockFrame = Frame(RightFrame,background='white')#'blue')
		ClockFrame.pack(side="top",fill='x')


		DateTextv = StringVar()
		DateText=Label(ClockFrame, background='white',textvariable=DateTextv,font=('Arial', 15, "bold"))
		DateText.pack(side="right",padx=15)

		BTCimageData=ImageTk.PhotoImage(Image.open(os.path.join(os.path.dirname(__file__), "BitcoinLogoRound.png")))
		BTCimage = Label(LeftFrame, image = BTCimageData,borderwidth=0,background='white')#'black')
		BTCimage.pack(side="top",padx=(10,0),pady=10, anchor="nw")


		Header=Label(RightFrame, background='white',text='Distributed Charge',font=('Courier', 80, "bold"))
		Header.pack(anchor='center',pady=(35,20))

		SmallHeader=Label(RightFrame, background='white',text='~ Electric Vehicle Charging Using Bitcoin Micropayments Over The Lightning Network ~',font=('Helvetica', 20, "bold"))
		SmallHeader.pack(anchor='center',pady=10)


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		BigStatusText=Label(MiddleFrame, background='white',textvariable=BigStatusTextv,font=('Helvetica', 80))
		BigStatusText.pack(anchor='n',pady=(0,10))

		SmallStatusText=Label(MiddleFrame,background='white',textvariable=SmallStatusTextv,font=('Helvetica', 40))
		SmallStatusText.pack(anchor="n",pady=(10,30))


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		UnitSpecificationsv = StringVar()
		UnitSpecifications=Label(MiddleFrame,textvariable=UnitSpecificationsv,font=('Courier', 30),justify='left', background='white')#'red')
		UnitSpecifications.pack(side='left',anchor='s',padx=(40,0))



		OperatingConditionsv = StringVar()
		OperatingConditions=Label(MiddleFrame,textvariable=OperatingConditionsv,font=('Courier', 30),justify='left', background='white')#'red')
		OperatingConditions.pack(side='right',anchor='s',padx=(0,40))


		Frame(BottomFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		WebsiteText=Label(BottomFrame,background='white',text='http://AndySchroder.com/DistributedCharge/',font=('Courier', 20))
		WebsiteText.pack(side="left", anchor="sw",padx=10,pady=10)

		AUSimage=ImageTk.PhotoImage(Image.open(os.path.join(os.path.dirname(__file__), "A.U.S-small.png")))
		AUS = Label(BottomFrame, image = AUSimage,borderwidth=0)
		AUS.pack(side="right", anchor="se",padx=10,pady=10)






		ChargeTimeText=FormatTimeDeltaToPaddedString(timedelta(seconds=0))

		while True:

			DateTextv.set(datetime.now().strftime('%Y.%m.%d  -  %H.%M.%S'))

			BigStatusTextv.set(self.BigStatus)				
			SmallStatusTextv.set(self.SmallStatus)




			if (self.Volts is not None) and (self.Amps is not None) and (self.MaxAmps is not None):
				VoltsPrint=self.Volts
				AmpsPrint=self.Amps
				MaxAmpsPrint=self.MaxAmps
			else:
				VoltsPrint=0
				AmpsPrint=0
				MaxAmpsPrint=0

			PowerPrint=VoltsPrint*AmpsPrint
			MaxPowerPrint=VoltsPrint*MaxAmpsPrint

			UnitSpecificationsText=(
					#		'Current Type: Alternating, Single Phase\n'+
							'Max Power:    '+RoundAndPadToString(MaxPowerPrint/1000.,DecimalPlaces=1,LeftPad=3)+' kW\n'+
							'Max Current:  '+RoundAndPadToString(MaxAmpsPrint,DecimalPlaces=1,LeftPad=3)+' Amps RMS\n'+
							'\n'+
							'\n'+
							'\n'
				)

			UnitSpecificationsText+=	'Sale Rate:    '
			if self.CurrentRate>0:
				UnitSpecificationsText+=RoundAndPadToString(self.CurrentRate,DecimalPlaces=1,LeftPad=3)+' sat/(W*hour)'
			UnitSpecificationsText+=	'\n'

			UnitSpecificationsText+=	'Payment Size: '
			if self.RequiredPaymentAmount>0:
				UnitSpecificationsText+=RoundAndPadToString(self.RequiredPaymentAmount,DecimalPlaces=1,LeftPad=3)+' sat'
			UnitSpecificationsText+=	'\n'

			UnitSpecificationsv.set(UnitSpecificationsText)





			if self.ChargeStartTime !=-1 and self.Proximity is True:
				ChargeTimeText=FormatTimeDeltaToPaddedString(timedelta(seconds=round((datetime.now()-self.ChargeStartTime).total_seconds())))	#round to the nearest second, then format as a zero padded string

			OperatingConditionsText=(
					'Power:            '+RoundAndPadToString(PowerPrint/1000.,DecimalPlaces=1,LeftPad=6)+' kW\n'+
					'Current:          '+RoundAndPadToString(AmpsPrint,DecimalPlaces=1,LeftPad=6)+' Amps  RMS\n'+
					'Line Voltage:     '+RoundAndPadToString(VoltsPrint,DecimalPlaces=1,LeftPad=6)+  ' Volts RMS\n'+
					'\n'+
					'Energy Delivered: '+RoundAndPadToString(self.EnergyDelivered,DecimalPlaces=1,LeftPad=6)+' W*hour\n'+
					'Energy Paid For:  '+RoundAndPadToString(self.EnergyPaidFor,DecimalPlaces=1,LeftPad=6)+' W*hour\n'+
					'Payments:         '+RoundAndPadToString(self.EnergyPaidFor*self.CurrentRate,DecimalPlaces=1,LeftPad=6)+' sat\n'+
					'Charging Time:     '+' '+ChargeTimeText+''
				)

			OperatingConditionsv.set(OperatingConditionsText)


#need some more specific testing here because could catch other things
			try:	#seems to fail if the window was closed
				GUI.update_idletasks()
				GUI.update()
			except:
				#window was closed, so tell the thread to exit
				self._stop_event.set()

			if self._stop_event.is_set():	#exit the thread
				break

			sleep(0.25)			#only update screen 4 times per second




GUIThread=GUIClass()			#create the thread




