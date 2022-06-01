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

		self.screenscaling=0.4

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
		if False:
			GUI.geometry('1900x1025+0+0')
		else:
			#full screen
			GUI.overrideredirect(True)
			GUI.geometry('{0}x{1}+0+0'.format(GUI.winfo_screenwidth(),GUI.winfo_screenheight()))


		GUI.configure(background='white')#'green')

		TopFrame = Frame(GUI,background='white')#'orange')
		TopFrame.pack(side="top",anchor='n',fill='x')

		MiddleFrame = Frame(GUI,background='white')
		MiddleFrame.pack(side="top",anchor='s',fill='both',expand=True,pady=(int(30*self.screenscaling),int(30*self.screenscaling)))

		BottomFrame = Frame(GUI,background='white')#'grey')
		BottomFrame.pack(side="bottom",anchor='s',fill='x')


		LeftFrame = Frame(TopFrame,background='white')#'black')
		LeftFrame.pack(side="left")

		RightFrame = Frame(TopFrame,background='white')#'blue')
		RightFrame.pack(side="right",fill='x', expand=True)

		ClockFrame = Frame(RightFrame,background='white')#'blue')
		ClockFrame.pack(side="top",fill='x')


		DateTextv = StringVar()
		DateText=Label(ClockFrame, background='white',textvariable=DateTextv,font=('Arial', int(15*self.screenscaling), "bold"))
		DateText.pack(side="right",padx=int(15*self.screenscaling))




		BTCImageData = Image.open(os.path.join(os.path.dirname(__file__), "BitcoinLogoRound.png"))
		BTCImageData_resized = BTCImageData.resize((int(BTCImageData.width*self.screenscaling), int(BTCImageData.height*self.screenscaling)),Image.LANCZOS)		#think LANCZOS will give you a slightly different pixel count than requested because the request can be overconstrained if width and height don't have a common multiple(?) with self.screenscaling. need to research/think about more.
		BTCPhotoImage=ImageTk.PhotoImage(BTCImageData_resized)	#has to be on a separate line, can't be combine with the next, not sure why.
		BTCimage = Label(LeftFrame, image = BTCPhotoImage,borderwidth=0,background='white')#'black')
		BTCimage.pack(side="top",padx=(int(10*self.screenscaling),int(0*self.screenscaling)),pady=int(10*self.screenscaling), anchor="nw")


		Header=Label(RightFrame, background='white',text='Distributed Charge',font=('Courier', int(80*self.screenscaling), "bold"))
		Header.pack(anchor='center',pady=(int(35*self.screenscaling),int(20*self.screenscaling)))

		SmallHeader=Label(RightFrame, background='white',text='~ Electric Vehicle Charging Using Bitcoin Micropayments Over The Lightning Network ~',font=('Helvetica', int(20*self.screenscaling), "bold"))
		SmallHeader.pack(anchor='center',pady=int(10*self.screenscaling))


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		BigStatusText=Label(MiddleFrame, background='white',textvariable=BigStatusTextv,font=('Helvetica', int(80*self.screenscaling)))
		BigStatusText.pack(anchor='n',pady=(int(0*self.screenscaling),int(10*self.screenscaling)))

		SmallStatusText=Label(MiddleFrame,background='white',textvariable=SmallStatusTextv,font=('Helvetica', int(40*self.screenscaling)))
		SmallStatusText.pack(anchor="n",pady=(int(10*self.screenscaling),int(30*self.screenscaling)))


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		UnitSpecificationsv = StringVar()
		UnitSpecifications=Label(MiddleFrame,textvariable=UnitSpecificationsv,font=('Courier', int(30*self.screenscaling)),justify='left', background='white')#'red')
		UnitSpecifications.pack(side='left',anchor='s',padx=(int(40*self.screenscaling),int(0*self.screenscaling)))



		OperatingConditionsv = StringVar()
		OperatingConditions=Label(MiddleFrame,textvariable=OperatingConditionsv,font=('Courier', int(30*self.screenscaling)),justify='left', background='white')#'red')
		OperatingConditions.pack(side='right',anchor='s',padx=(int(0*self.screenscaling),int(40*self.screenscaling)))


		Frame(BottomFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		WebsiteText=Label(BottomFrame,background='white',text='http://AndySchroder.com/DistributedCharge/',font=('Courier', int(20*self.screenscaling)))
		WebsiteText.pack(side="left", anchor="sw",padx=int(10*self.screenscaling),pady=int(10*self.screenscaling))


		AUSImageData = Image.open(os.path.join(os.path.dirname(__file__), "A.U.S-small.png"))
		AUSImageData_resized = AUSImageData.resize((int(AUSImageData.width*self.screenscaling), int(AUSImageData.height*self.screenscaling)),Image.LANCZOS)		#think LANCZOS will give you a slightly different pixel count than requested because the request can be overconstrained if width and height don't have a common multiple(?) with self.screenscaling. need to research/think about more.
		AUSPhotoImage=ImageTk.PhotoImage(AUSImageData_resized)	#has to be on a separate line, can't be combine with the next, not sure why.
		AUSimage = Label(BottomFrame, image = AUSPhotoImage,borderwidth=0)
		AUSimage.pack(side="right", anchor="se",padx=int(10*self.screenscaling),pady=int(10*self.screenscaling))






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




