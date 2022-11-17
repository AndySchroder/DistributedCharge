Change Log
===========


v0.12-beta
----------
Initial GRID Release
 - Dynamic pricing: Buyer and the seller agree to a sale period and a constant, piecewise linear, or sinusoidal rate profile within the sale period.
 - The RateFile is automatically reloaded every time it is saved and any changes will be applied when the current sale period ends and a new sale period is negotiated.
 - Store settings in a config file instead of hardcoding in scripts.
 - SSL encrypted and authenticated communication between the buyer and seller over TCP.
 - Smart Load controller.
 - Power flow controlled by relays on Board A0.
 - Power measurement using EKM Metering OmniMeter Pulse v.4, connected via Board A0.
 - Note: EV version is broken in this release and will be fixed in a later release.


v0.11-beta
----------
Board A0 EV Release
 - Removed the use of LabJack and replaced it with Board A0 and the raspberry pi compute module 4.
 - Improved robustness and logging.
 - Reworked screen layout for lower resolution.
 - Improved startup scripts.


v0.10-alpha
-----------
Initial EV Release




