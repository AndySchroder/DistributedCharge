


###############################################################################
###############################################################################
# Copyright (c) 2024, Andy Schroder
# See the file README.md for licensing information.
###############################################################################
###############################################################################




from time import sleep
from datetime import datetime,timedelta

import threading,os,logging,sys,subprocess

from PIL import ImageTk, Image
from tkinter import Tk,StringVar,Label,CENTER,Frame,LEFT,BOTH

from helpers2 import FormatTimeDeltaToPaddedString,RoundAndPadToString,FullDateTimeString




import qrcode



logger = logging.getLogger(__name__)




TitleText=False









class GUIClass(threading.Thread):
	#this class operates in another thread in daemon mode, and will shutdown if the .stop() method is used.
	#see also notes about stoppable threads in the ReceiveInvoices class


	def __init__(self, arguments, *args, **kwargs):
		super(GUIClass, self).__init__(*args, **kwargs)
		self._stop_event = threading.Event()

		self.daemon=True		# using daemon mode so control-C will stop the script and the threads and .join() can timeout.


		#initialize variables, trying to make them match the main scripts initial values, although don't know if it really matters
		self.Volts=0
		self.Amps=0
		self.Power=0
		self.BigStatus=''
		self.SmallStatus=''
		self.EnergyDelivered=0

		self.SettledPayments=0
		self.HeldPayments=0
		self.CanceledPayments=0
		self.CreditRemaining=0


		self.EnergyCost=0
		self.RecentRate=0
		self.RequiredPaymentAmount=0
		self.ChargeStartTime=-1
		self.ChargeTimeText=FormatTimeDeltaToPaddedString(timedelta(seconds=0))


		self.HTLCTimeRemaining=0
		self.HTLCTimeRemainingText=''


		self.MaxAmps=0

		self.WindowTitle='Distributed Charge'

		self.DCGeneratorVoltage=0


		self.OLDQRLink='initial'	# make it something different so as to trigger a blank image to be generated
		self.QRLink=None

		self.InvoiceExpirationText=''


		self.arguments=arguments



	def stop(self,event=None):
		logger.info('GUI stop requested')
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()


	def update(self):
		if not self.stopped():
			self.Window.update_idletasks()
			self.Window.update()
			return True
		else:
			return False


	def toggleFullscreen(self,event=None):

		if not self.Window.attributes('-fullscreen'):
			self.Window.attributes('-fullscreen', True)
		else:
			self.Window.attributes('-fullscreen', False)




	def run(self):


		self.Window=Tk()

		self.Window.title(self.WindowTitle)

		# allow shutdown by escape key or window closure.
		self.Window.bind('<Escape>', self.stop)
		self.Window.bind('<Control-c>', self.stop)
		self.Window.protocol("WM_DELETE_WINDOW", self.stop)

		# allow toggle of fullscreen
		self.Window.bind('<Double-Button-1>', self.toggleFullscreen)
		self.Window.bind('f', self.toggleFullscreen)
		self.Window.bind('F', self.toggleFullscreen)		# alternate solution if need to do this for a lot of keys: https://stackoverflow.com/questions/7402516/tkinter-case-insensitive-bind/24804104#24804104







		# need to set the geometry before maximizing
		if self.arguments.geometry is None:
			# start with some sensible window geometry by default.
			self.Window.geometry('{0}x{1}+{2}+{3}'.format(int(self.Window.winfo_screenwidth()*.8),int(self.Window.winfo_screenheight()*.8),int(self.Window.winfo_screenwidth()*.05),int(self.Window.winfo_screenheight()*.05)))
		else:
			# apply user defined geometry if passed on the command line.
			self.Window.geometry(self.arguments.geometry)


		if self.arguments.maximized:
			self.Window.attributes('-zoomed', True)
			# for some reason need to maximize AND update before entering full screen, otherwise it won't be maximized when exiting full screen
			# this will cause a slight flicker as you see it transition from maximized to fullscreen on startup, but it is considered the
			# more desireable outcome.
			self.update()


		if self.arguments.fullscreen:

			# turn off monitor screen saver. can't figure out the correct config file to edit, but it works when place here, so it is fine
			subprocess.run(['xset','s','off'], check=True)			# don't activate screensaver
			subprocess.run(['xset','-dpms'], check=True)			# disable DPMS (Energy Star) features.
			subprocess.run(['xset','s','noblank'], check=True)		# don't blank the video device

			# always starts not in full screen, so can just run this.
			self.toggleFullscreen()


		# update now so can get the current window dimensions so that the scaling can be applied
		self.update()








		BigStatusTextv = StringVar()
		SmallStatusTextv = StringVar()






		self.Window.configure(background='white')#'green')

		# don't know that can add padding to an entire window, so just put everything in a frame and add padding to that
		MainFrame = Frame(self.Window,background='white')#'orange')
		MainFrame.pack(fill=BOTH,expand=True,padx=0,pady=0)

		TopFrame = Frame(MainFrame,background='white')#'orange')
		TopFrame.pack(side="top",anchor='n',fill='x')

		MiddleFrame = Frame(MainFrame,background='white')
		MiddleFrame.pack(side="top",anchor='s',fill='both',expand=True)


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		MiddleMiddleFrame = Frame(MiddleFrame,background='white')
#		MiddleMiddleFrame.place(relx=0.5, rely=0.5, anchor=CENTER)
		MiddleMiddleFrame.pack(side="top",anchor='n',fill='both',expand=False)



		FooterFrame = Frame(MainFrame,background='white')#'grey')
		FooterFrame.pack(side="bottom",anchor='s',fill='x')

		BottomFrame = Frame(MainFrame,background='white')#'grey')
		BottomFrame.pack(side="bottom",anchor='s',fill='x')

		LeftFrame = Frame(TopFrame,background='white')#'black')
		LeftFrame.pack(side="left")

		RightFrame = Frame(TopFrame,background='white')#'blue')
		RightFrame.pack(side="right",anchor='ne',fill=BOTH, expand=True)

		ClockFrame = Frame(RightFrame,background='white')#'blue')
		ClockFrame.pack(side="top",fill='x')


		DateTextv = StringVar()
		DateText=Label(ClockFrame, background='white',textvariable=DateTextv)
		DateText.pack(side="right",anchor='ne')


		if TitleText:
			BTCImageData = Image.open(os.path.join(os.path.dirname(__file__), "BitcoinLogoRound.png"))
			BTCimage = Label(LeftFrame, borderwidth=0,background='white')#'black')
			BTCimage.pack(side="top", anchor="w")

			Header=Label(RightFrame, background='white',text='Distributed Charge')
			Header.place(relx=0.5, rely=0.5, anchor=CENTER)





		BigStatusText=Label(MiddleMiddleFrame, background='white',textvariable=BigStatusTextv)
		BigStatusText.pack(anchor='n')

		SmallStatusText=Label(MiddleMiddleFrame,background='white',textvariable=SmallStatusTextv)
		SmallStatusText.pack(anchor="n")


		Frame(MiddleFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		UnitSpecificationsv = StringVar()
		UnitSpecifications=Label(BottomFrame,textvariable=UnitSpecificationsv,justify='left', background='white')#'red')
		UnitSpecifications.pack(side='left',anchor='s')



		OperatingConditionsv = StringVar()
		OperatingConditions=Label(BottomFrame,textvariable=OperatingConditionsv,justify='left', background='white')#'red')
		OperatingConditions.pack(side='right',anchor='s')







#		Frame(FooterFrame,background='black').pack(side="top",anchor='n',fill='x')	#horizontal line


		if TitleText:
			WebsiteText=Label(FooterFrame,background='white',text='http://AndySchroder.com/DistributedCharge/')
			WebsiteText.pack(side="left", anchor="sw")

			AUSImageData = Image.open(os.path.join(os.path.dirname(__file__), "A.U.S-small.png"))
			AUSimage = Label(FooterFrame,borderwidth=0)
			AUSimage.pack(side="right", anchor="se")

















		InvoiceExpirationsv = StringVar()
		InvoiceExpiration=Label(BottomFrame,textvariable=InvoiceExpirationsv,justify='center', background='white')#'red')
		InvoiceExpiration.pack(side='bottom',anchor='s')


		QRimage = Label(BottomFrame,borderwidth=10,background='white')#'black')
		QRimage.pack(side='bottom',anchor="s")

















		while True:

			DateTextv.set(FullDateTimeString(datetime.now()))

			BigStatusTextv.set(self.BigStatus)				
			SmallStatusTextv.set(self.SmallStatus)




			# car.py and wall.py set Volts and Amps to None if there is no
			# measurements available yet because don't want to integrate them
			# and compute a bogus EnergyDelivered reading. however, here zero
			# is just displayed.
			if (self.Volts is not None) and (self.Amps is not None):
				VoltsPrint=self.Volts
				AmpsPrint=self.Amps
			else:
				VoltsPrint=0
				AmpsPrint=0

			MaxPowerPrint=VoltsPrint*self.MaxAmps

			UnitSpecificationsText=(
					#		'Current Type: Alternating, Single Phase\n'+
							'Max Power:    '+RoundAndPadToString(MaxPowerPrint/1000.,DecimalPlaces=1,LeftPad=3)+' kW\n'+
							'Max Current:  '+RoundAndPadToString(self.MaxAmps,DecimalPlaces=1,LeftPad=3)+' Amps RMS\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'+
							'\n'
				)

			UnitSpecificationsText+=	'Sale Rate:   '
			if self.RecentRate>0:
				UnitSpecificationsText+=RoundAndPadToString(self.RecentRate*1000,DecimalPlaces=0,LeftPad=5)+' sat/(kW*hour)'
			UnitSpecificationsText+=	'\n'

			if self.RequiredPaymentAmount>0:
				UnitSpecificationsText+=	'Payment Size: '
				UnitSpecificationsText+=RoundAndPadToString(self.RequiredPaymentAmount,DecimalPlaces=0,LeftPad=4)+' sat'
			UnitSpecificationsText+=	'\n'

			UnitSpecificationsv.set(UnitSpecificationsText)





			if self.ChargeStartTime !=-1 and self.Connected is True:
				self.ChargeTimeText=FormatTimeDeltaToPaddedString(timedelta(seconds=round((datetime.now()-self.ChargeStartTime).total_seconds())))	#round to the nearest second, then format as a zero padded string

			OperatingConditionsText=(
					'Power:           '+RoundAndPadToString(self.Power/1000.,DecimalPlaces=3,LeftPad=6)+' kW\n'+
					'Current:         '+RoundAndPadToString(AmpsPrint,DecimalPlaces=2,LeftPad=6)+'  Amps  RMS\n'+
					'Line Voltage:    '+RoundAndPadToString(VoltsPrint,DecimalPlaces=2,LeftPad=6)+  '  Volts RMS\n'+
					'\n'+
					'Energy Delivered: '+RoundAndPadToString(self.EnergyDelivered,DecimalPlaces=0,LeftPad=7)+'  W*hour\n'+
					'Energy Cost:      '+RoundAndPadToString(self.EnergyCost,DecimalPlaces=0,LeftPad=7)+'  sat\n'+
					'Settled Payments: '+RoundAndPadToString(self.SettledPayments,DecimalPlaces=0,LeftPad=7)+'  sat\n'+
					'Held Deposits:    '+RoundAndPadToString(self.HeldPayments,DecimalPlaces=0,LeftPad=7)+'  sat\n'+
					'Canceled Deposits:'+RoundAndPadToString(self.CanceledPayments,DecimalPlaces=0,LeftPad=7)+'  sat\n'+
					'Credit Remaining: '+RoundAndPadToString(self.CreditRemaining,DecimalPlaces=0,LeftPad=7)+'  sat\n'+
					'Session Time:     '+self.ChargeTimeText+'\n'+
#					'Remaining Time:   '+FormatTimeDeltaToPaddedString(self.HTLCTimeRemaining)+
					'Remaining Time: '+self.HTLCTimeRemainingText+
					'\n'+
					'\n'+
					''
				)

			OperatingConditionsv.set(OperatingConditionsText)




			InvoiceExpirationsv.set(self.InvoiceExpirationText)

















			# adjust the scaling based on the window dimensions
			# IMPORTANT: need to limit to screenwidth and screenheight with min() because otherwise it will grow infinitely and crash the system if no geometry specified because then
			# the tk window keeps auto adjusting to the new (larger) font size if no geometry is specified.
			# sensible geometry is applied above as a default if none is specified on the command line, so things are okay.
			# it was harder to find this sensitivity because tk doesn't seem to do continuously variable fonts AND maybe because the screenscaling is computed based on the minimum of the width and the height. 
			# also, when exploring this, discovered that if the font size goes to 0 then a default size applies, so it jumps back up. so, the smallest font size text on the screen will reach that first and
			# then it will get confusing because it is suddenly bigger than the text it is supposed to be smaller than.
			if TitleText:
				baseScreenscaling=0.400
			else:
				baseScreenscaling=0.475
			self.screenscaling=baseScreenscaling*min(min(self.Window.winfo_width(),self.Window.winfo_screenwidth())/800,min(self.Window.winfo_height(),self.Window.winfo_screenheight())/480)

#			print(self.screenscaling)


















			if self.OLDQRLink != self.QRLink:

				self.OLDQRLink=self.QRLink

				if self.QRLink is not None:
					qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4,)
					qr.add_data(self.QRLink)
					qr.make(fit=True)
					img = qr.make_image(fill_color="black", back_color="white")

					ExtraImageScaling=0.6*.9

					QRImageData_resized = img.resize((int(img.size[0]*self.screenscaling*ExtraImageScaling), int(img.height*self.screenscaling*ExtraImageScaling)),Image.LANCZOS)

					QRPhotoImage=ImageTk.PhotoImage(QRImageData_resized)


				else:
					#blank image
					QRPhotoImage=ImageTk.PhotoImage(Image.new("RGB", (10, 10), (255, 255, 255)))


				QRimage.configure(image=QRPhotoImage)
				QRimage.pack_configure(padx=(int(10*self.screenscaling),int(0*self.screenscaling)),pady=(int(0*self.screenscaling),int(0*self.screenscaling)))
















			# apply the scaling
			MiddleFrame.pack_configure(pady=(int((30-20)*self.screenscaling),int((30-20)*self.screenscaling)))

			DateText.configure(font=('Arial', int(25*self.screenscaling), "bold"))
			DateText.configure(padx=int(15*self.screenscaling))


			if TitleText:
				BTCImageData_resized = BTCImageData.resize((int(BTCImageData.width*self.screenscaling), int(BTCImageData.height*self.screenscaling)),Image.LANCZOS)		#think LANCZOS will give you a slightly different pixel count than requested because the request can be overconstrained if width and height don't have a common multiple(?) with self.screenscaling. need to research/think about more.
				BTCPhotoImage=ImageTk.PhotoImage(BTCImageData_resized)	#has to be on a separate line, can't be combine with the next, not sure why.
				BTCimage.configure(image = BTCPhotoImage)
				BTCimage.pack_configure(padx=(int(10*self.screenscaling),int(0*self.screenscaling)),pady=int(10*self.screenscaling))

				Header.configure(font=('Courier', int(80*self.screenscaling), "bold"))
				Header.pack_configure(pady=(int(35*self.screenscaling),int(20*self.screenscaling)))


			BigStatusText.configure(font=('Helvetica', int((40)*self.screenscaling*2.25/(1+self.BigStatus.count('\n')))))
			BigStatusText.pack_configure(pady=(int(2*self.screenscaling),int(2*self.screenscaling)))

			SmallStatusText.configure(font=('Helvetica', int(25*self.screenscaling)))
			SmallStatusText.pack_configure(pady=(int(2*self.screenscaling),int(2*self.screenscaling)))

			UnitSpecifications.configure(font=('Courier', int(20*self.screenscaling)))
			UnitSpecifications.pack_configure(padx=(int(4*self.screenscaling),int(0*self.screenscaling)))

			OperatingConditions.configure(font=('Courier', int(20*self.screenscaling)))
			OperatingConditions.pack_configure(padx=(int(0*self.screenscaling),int(4*self.screenscaling)))


			InvoiceExpiration.configure(font=('Courier', int(20*self.screenscaling)))
			InvoiceExpiration.pack_configure(padx=(int(0*self.screenscaling),int(10*self.screenscaling)))
			InvoiceExpiration.pack_configure(pady=(int(0*self.screenscaling),int(0*self.screenscaling)))



			if TitleText:
				WebsiteText.configure(font=('Courier', int(20*self.screenscaling)))
				WebsiteText.pack_configure(padx=int(10*self.screenscaling),pady=int(10*self.screenscaling))

				AUSImageData_resized = AUSImageData.resize((int(AUSImageData.width*self.screenscaling), int(AUSImageData.height*self.screenscaling)),Image.LANCZOS)		#think LANCZOS will give you a slightly different pixel count than requested because the request can be overconstrained if width and height don't have a common multiple(?) with self.screenscaling. need to research/think about more.
				AUSPhotoImage=ImageTk.PhotoImage(AUSImageData_resized)	#has to be on a separate line, can't be combine with the next, not sure why.
				AUSimage.configure(image = AUSPhotoImage)
				AUSimage.pack_configure(padx=int(10*self.screenscaling),pady=int(10*self.screenscaling))

















			# now update
			if not self.update():
				# if the didn't succeed then the GUI stopped and need to quit
				logger.info('stopping GUI')
				sys.exit()

			sleep(0.50)












