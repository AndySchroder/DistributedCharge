<pre>
   title: Distributed Charge - EV, Payment Module Setup Instructions
   date: 2025-12-13
</pre>


# System Setup #

## Operating System ##

### CM4 System Disk Imaging and Setup (from your desktop/laptop computer) ###

- Install `mkpasswd` and `arp-scan`
   - `sudo apt update`
   - `sudo apt install whois arp-scan`
- Generate a hashed password for the system login
   - `mkpasswd --method=SHA-512 --rounds=4096`
- Generate an ssh public key
   - `ssh-keygen -t ed25519`
      - `Enter file in which to save the key`
         - `demo`
      - `Enter passphrase (empty for no passphrase)`
         - ENTER
      - `Enter same passphrase again`
         - ENTER
- Show the generated ssh public key
   - `cat demo.pub`
- Download the Ubuntu Server 22.04.5 image file.
    - `wget http://cdimage.ubuntu.com/releases/22.04.5/release/ubuntu-22.04.5-preinstalled-server-arm64+raspi.img.xz`
- Download the checksum and signature files.
    - `wget http://cdimage.ubuntu.com/releases/22.04.5/release/SHA256SUMS`
    - `wget http://cdimage.ubuntu.com/releases/22.04.5/release/SHA256SUMS.gpg`
- Verify the downloaded image file using the checksum and signature files (you need to already have the Ubuntu signing key in your gpg keyring).
    - `gpg --keyid-format long --verify SHA256SUMS.gpg SHA256SUMS`
        - Look for `Good signature` in the output.
    - `sha256sum -c SHA256SUMS 2>&1 | grep OK`
        - Look for `ubuntu-22.04.5-preinstalled-server-arm64+raspi.img.xz: OK` in the output.
- Unzip the image file.
    - `unxz ubuntu-22.04.5-preinstalled-server-arm64+raspi.img.xz`
- Check what disks are attached to your system by running `lsblk`.
- Boot the CM4 in a special mode so that it attaches the eMMC disk to the USB-C port as a normal disk (see [eMMC boot](https://tofu.oratek.com/#/?id=emmc-boot) for how to do this with the TOFU).
   - Install `rpiboot`.
    - `sudo apt install rpiboot`
   - Run `rpiboot -l` in a new terminal.
   - Hold down the `nRPIBOOT` button while plugging the USB-C on the TOFU.
   - Release the `nRPIBOOT` button after you stop seeing new outputs from the `rpiboot` command in the terminal.
- Run `lsblk` again to check to see what disks are attached to your system. Comparing to the above output should allow you to determine what disk the CM4 eMMC is.
- Once you are certain you know the disk of the CM4 eMMC, image ubuntu server 22.04 onto the compute module, setting `of=` to the disk that corresponds to the CM4 eMMC. WARNING: don't mess up the `of=`  value as you will erase whatever disk you define there!
    - `sudo dd bs=100M if=ubuntu-22.04.5-preinstalled-server-arm64+raspi.img of=/dev/sdZ`
        - Warning: As noted above, make sure `Z` corresponds to the disk that corresponds to the CM4 eMMC!
        - Note: If this command runs successfully, no output will be produced in the terminal, it will just return to the command prompt.
- After imaging the disk but _before_ disconnecting the USB cable from your desktop/laptop computer, wait for the disk to appear mountable and then mount the disk and do the following:
   - Enable the DSI display interface that is used by Distributed Charge on the CM4 with Ubuntu 22.04.
      - Open a terminal.
      - Change directories to the root of the `system-boot` partition.
      - Run `wget https://datasheets.raspberrypi.com/cmio/dt-blob-disp1-only.bin -O dt-blob.bin` .
      - See also, https://github.com/raspberrypi/documentation/blob/5d9530343d5515acf11a5078762c8170b3c69354/documentation/asciidoc/computers/compute-module/cmio-display.adoc and https://tofu.oratek.com/#/?id=camera-and-display-ports .
   - Edit the file `user-data` in the root of the `system-boot` partition:

________________________________________________________________

__Remove__

```
chpasswd:
  expire: true
  users:
  - name: ubuntu
    password: ubuntu
    type: text
```

__Add__

```
hostname: dc-YourUniqueNameHere
users:
  - name: dc
    passwd: $6$rounds=4096$ILAfHKh2Be$jmH8fUyTMJO/.ZLA6neyADVfb5ZW0yB3RqCjiRXcvjeJVRivSW.yzZaa/rxszPdFKTFlTJ5YKSEJB4CfQk03f.    #'test' from `mkpasswd --method=SHA-512 --rounds=4096`
    groups: dialout,gpio,spi,sudo,plugdev
    lock_passwd: false
    shell: /bin/bash
    ssh_authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGJHjRE8uX5uknNkBE5uU0+WtyujWuwExb7lBMVCwabu

```
Note: replace `$6$rounds=4096$ILAfHKh2Be$jmH8fUyTMJO/.ZLA6neyADVfb5ZW0yB3RqCjiRXcvjeJVRivSW.yzZaa/rxszPdFKTFlTJ5YKSEJB4CfQk03f` with the output of `mkpasswd` from above and `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGJHjRE8uX5uknNkBE5uU0+WtyujWuwExb7lBMVCwabu` with the contents of `demo.pub` from above.

__Change__

`ssh_pwauth: true` to `ssh_pwauth: false`

(actually seems to already be set to `false` on Ubuntu Server 22.04.5, so you can probably skip this step)
________________________________________________________________

-
   - Save `user-data` .
   - Close any open terminal windows with a working directory of the disk.
   - Eject the disk and then remove the USB-C cable.
   - Stop `rpiboot` using `Control-C`.


### Connecting to the CM4 for the first time ###

- Boot the CM4 by plugging in power to the TOFU with a barrel connector and not the USB-C port.
   - The TOFU has poor power delivery on the USB-C port, and
   - using the USB-C port disables the other USB ports, so you can't plug a keyboard in and use it at the same time.
- At this point you have 2 options to begin using the CM4:
   - ssh
      - Notes:
         - Requires you to blindly trust the ssh public key fingerprint of the CM4, but this is not a huge risk if you are connecting to a local network that you control.
         - Allows you to copy and paste commands from your desktop/laptop and save the scrollback buffer.
      - Attach an ethernet cable to the TOFU that is connected to a network that provides DHCP and internet access.
      - Try to figure out (by using your router's configuration interface or scanning your network) what IP address your local network's DHCP server provided to the CM4 and ssh to that address.
         - `sudo arp-scan -lNx`
      - `ssh -i demo dc@IPAddress`
   - Keyboard + LCD screen
      - Notes:
         - Requires all commands to be manually typed into the keyboard. There is no scrollback buffer.
         - Screen size and resolution is very low.
      - Plug a USB keyboard into the TOFU and use the small screen.
      - Username: dc
      - Password: value used above when running `mkpasswd --method=SHA-512 --rounds=4096` and was installed into the file `user-data`.
      - You can now jump ahead to "Connect to the CM4 using ssh" if you attach an ethernet cable to the TOFU to login and authenticate via ssh in a more straightforward way than described above. After logging in via ssh, then return here and move forward with "Initial Steps".



### Initial Steps ###

- Firewall setup
   - Check the firewall status.
      - `sudo ufw status verbose`
   - Allow ssh connections.
      - `sudo ufw allow in 22/tcp`
   - Enable the firewall.
      - `sudo ufw enable`
         - Choose `y` when prompted with "Command may disrupt existing ssh connections. Proceed with operation (y|n)?".
   - Check the firewall is running and that ssh has been allowed through the firewall.
      - `sudo ufw status verbose`
- If you have not already done so, attach an ethernet cable to the TOFU that is connected to a network that provides DHCP and internet access.



### Update the Package Lists ###

`sudo apt update`



### Remove auto updates/backdoors ###

`sudo apt purge -y snapd unattended-upgrades`



### Install basic utilities ###

`sudo apt install -y x11-xserver-utils xterm xinit vim git jq python3-pip build-essential cmake g++ libpcsclite-dev libcurl4-openssl-dev libmbim-utils network-manager can-utils python3-tk python3-zmq python3-pystemd pkgconf libtool libzstd-dev liblzma-dev libssl-dev autoconf`



### Network Setup ###

- We installed Network Manager and will use it instead of systemd-network (for everything but the CAN bus interfaces) because Network Manager supports cellular radios and also has simple setup of WiFi and Wireguard network interfaces.
   - Switch to Network Manager
      - `sudo sh -c "echo 'network:\n    version: 2\n    renderer: NetworkManager\n' > /etc/netplan/50-cloud-init.yaml"`
      - `sudo netplan apply`
   - Get the MAC address of the ethernet adapter
      - `ip -c l show eth0`
   - Make Network Manager realize it now can manage the ethernet adapter
      - `sudo systemctl restart NetworkManager`
   - Reconnect ethernet using network manager
      `sudo nmcli device connect eth0`
   - If you are using ssh your connection will now likely hang and eventually disconnect because the IP address that your local DHCP server hands out to Network Manager might be different than what it gave to systemd-networkd.
      - Find the new IP address of the ethernet interface
         - `sudo arp-scan -lNx|grep -i eth0MACADDRESS`
      - Reconnect using the new IP address of the ethernet interface
         - `ssh -o VisualHostKey=yes -i demo dc@NewIPAddress`
         - You will need to re-trust the public key fingerprint of the CM4 for this new IP address
   - Don't wait for systemd-networkd to bring interfaces online during boot since we won't be using systemd-networkd (NetworkManager-wait-online.service is used instead). Note, this step is needed in Ubuntu 22.04 because it does not yet have https://github.com/systemd/systemd/pull/25830 which fixes the issue.
      - `sudo systemctl disable systemd-networkd-wait-online.service`
      - `sudo systemctl mask systemd-networkd-wait-online.service`
- Configure Cellular (optional):
   - Compile and install `lpac` and `lpac-libmbim-wrapper` for provisioning eSIM profiles (optional).
      - `git clone https://github.com/AndySchroder/lpac`
      - `cd lpac`
      - `cmake . -DCPACK_GENERATOR=DEB`
      - `make -j package`
      - `sudo dpkg -i lpac_X.X.X_arm64.deb`
      - `cd ..`
      - `sudo pip3 install git+https://github.com/stich86/lpac-libmbim-wrapper.git`
      - Verify the modem number is `0` with `mmcli -L`
      - Find the MBIMdevice port of the modem by running `mmcli -m 0 -J|jq '.modem.generic.ports'|grep mbim`.
      - Purchase a DATA.PLUS eSIM from https://silent.link/ .
      - Follow the directions at https://github.com/estkme-group/lpac/blob/main/docs/USAGE.md to interact with the eSIM, but instead use `sudo lpac-mbim --device=/dev/MBIMdevice` in place of `lpac`.
      - After configuring the profile to the eSIM, reset the cellular radio with `sudo mmcli -m 0 -r`
      - Wait for the modem to be reset and change to modem number `1` with `watch mmcli -L`.
   - Configure the cellular network interface
      - `sudo nmcli c add type gsm ifname '*' con-name Cellular apn YourCellularAPNHere`
         - For silent.link, use `plus` in place of `YourCellularAPNHere`.
      - `sudo nmcli c modify Cellular connection.autoconnect yes`
- Use StaticWire for obtaining a dedicated public static IP address using a wireguard tunnel (optional):
   - Install StaticWire
      - `pip3 install git+https://github.com/AndySchroder/StaticWire.git`
   - Logout
      - `exit`
   - Log back in
      - Use either the Keyboard + LCD screen or ssh as you did previously.
      - This step is required to get `/home/dc/.local/bin/` automatically put into `$PATH` so that the new `staticIP` executable can be found.
   - Follow the usage instructions at https://github.com/AndySchroder/StaticWire .
   - Notes:
      - StaticWire allows you to access the CM4 from any internet connection, not just your local network.
      - The QR code from the `staticIP AddCredit` command does not work on the small built in screen, you will need to use ssh from a laptop.
- Configure WiFi Client (optional):
   - `nmcli device wifi list`
      - Shows WiFi networks within range.
   - `sudo nmcli device wifi connect "YourNetworkSSID" password "YourPassword"`
      - Connects to a WiFi network.
   - Check connections with `nmcli` or `nmcli c`.
- Configure WiFi Hotspot (optional):
   - Only works if you did not configure a WiFi Client above.
   - Configure if you want to be able to create a WiFi access point on your Payment Module to connect directly to it with your laptop.
   - Useful if your laptop does not have cellular internet and there is no WiFi network to be a client of nearby (or the WiFi network nearby has a poor signal at the Payment Module).
   - Will be much faster than using cellular on your laptop (if your laptop has it)
   - If you use StaticWire and the routed hotspot option, you can connect to the payment module using the public IP address for the StaticWire tunnel and it will automatically bypass the tunnel since it knows that you are directly connected (making it faster).
   - Use the payment module as a WiFi general internet connection for your laptop (for more than just doing debugging on the Payment Module)
   - Option 1 - Passthrough hotspot using a **Bridge** interface
      - Use this option if you have a wired ethernet internet that already has a router installed which will be running a DHCP server that can provide more (usually private) IP addresses to the WiFi clients that will be connecting to your new access point. This option is useful if you have existing wireless access points on your network that you would like to share the same SSID and password with so that seamless roaming can occur at your site from the existing access points to this new access point.
      - This option also allows direct connection to the clients on your new access point from the rest of the network.
      - Steps to setup
         - Rename the existing ethernet connection and make it not autoconnect
            - `sudo nmcli connection modify "eth0" connection.id "Ethernet-non-bridged" connection.autoconnect no`
         - Setup the bridge interface
            - `sudo nmcli connection add type bridge con-name 'Bridge' ifname bridge0 connection.autoconnect-slaves yes`
         - Create access point and attach to the bridge interface
            - `sudo nmcli connection add con-name 'Hotspot-Bridged' ifname wlan0 type wifi slave-type bridge master bridge0 wifi.mode ap wifi.ssid YourSSIDName wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.psk YourPassword`
         - Attach ethernet to the bridge interface
            - `sudo nmcli connection add con-name 'Ethernet-Bridged' ifname eth0 type ethernet slave-type bridge master bridge0`
         - Get the MAC address of the new bridge interface (it does not have an IP address yet)
            - `ip -c l show bridge0`
            - NOTE: If you wait too long (a few minutes), the following command may not even be required and Ethernet-Bridged will automatically be brought up and you won't be able to run this command to find the MAC address if you are connected using ssh because Ethernet-non-bridged will be automatically brought down.
         - Bring the new bridged ethernet interface up
            - `sudo nmcli connection up Ethernet-Bridged`
         - If you are using ssh your connection will hang and eventually disconnect because the non-bridged ethernet interface must be brought down to do this.
            - Find the IP address of the bridge interface (the bridged ethernet interface does not have an IP address associated with it like the non-bridged ethernet interface did)
               - `sudo arp-scan -lNx|grep -i bridgeMACADDRESS`
            - Reconnect using the new IP address of the bridge interface
               - `ssh -o VisualHostKey=yes -i demo dc@NewIPAddress`
               - You will need to re-trust the public key fingerprint of the CM4 for this new IP address
   - Option 2 - Standalone routing hotspot using **Network Address Translation (NAT)**
      - Use this option if you only have a single IP address available and are trying to share a
        - cellular internet connection
        - wireguard tunnel, or
        - wired ethernet connection to a fiber optic, DSL, or coaxial intneret service with no router.
      - This option also firewalls the clients on your new access point from the rest of the network, so you may want to use it instead of a the **Bridge** alternative described above if you have a wired ethernet internet that already has a router/DHCP server that can provide more IP addresses if you don't want the clients to be accessible and/or you don't want the router to know that they are there.
      - Steps to setup
         - Create the Hotspot connection:
            - `sudo nmcli d wifi hotspot ifname wlan0 ssid YourSSIDName password YourPassword`
         - If you have UFW (Uncomplicated FireWall) installed (which was recommended above), you will need to allow some things through the firewall in order for it to work.
            - Allow DHCP leases
               - `sudo ufw allow in on wlan0 to any port 67 proto udp`
            - Allow DNS
               - `sudo ufw allow in on wlan0 from 10.42.0.0/24 to any port 53`
            - Allow traffic to the internet
               - `sudo ufw route allow in on wlan0 from 10.42.0.0/24 out on sw_xxxxxxxxxx`
                  - `sw_xxxxxxxxxx` is the name of the wireguard tunnel interface setup with StaticWire. If you aren't using a wireguard tunnel, then you likely want to use `wwan0`, which is the cellular interface, or `eth0`, which is the ethernet interface. If you also aren't using cellular or ethernet, then you can skip this step. If you are using both cellular and ethernet without a wireguard tunnel, you can repeat this command multiple times.
            - Note: These rules will also allow traffic when the hotspot connection is off and and a WiFi client happens to be connected to a network with address 10.42.0.0/24. However, the routed traffic likely won't get very far because network address translation will be turned off when the hotspot connection is turned off and because 10.42.0.0/24 is not a publicly routable subnet. Also, the DHCP and DNS servers should be turned off if the hotspot connection is turned off. So, this does not seem to be a practical concern. Older versions of ubuntu seemed to setup these firewall rules automatically so this used to not even be something to consider, but in ubuntu 22.04, they seem to need to be explicitly defined.
         - Now that you have setup the connection, you can use it
            - Bring the Hotspot up
               - `sudo c u Hotspot`
                  - Don't do this if already connected as a client to a WiFi network. You must first run `sudo c d WiFiClientConnection` to disconnect from that network.
                  - Needs to be done on each boot unless you run `sudo nmcli c modify Hotspot connection.autoconnect yes`, but you can't do this if you have connected as a client to another network above.
               - Now you should see the SSID on your laptop and can connect to it.
            - Bring the Hotspot down
               - `sudo c d Hotspot`
- You may now remove the ethernet cable if you setup WiFi and/or Cellular.
- Connect to the CM4 using ssh (if you did not already do so above)
   - Check what IP addresses you have assigned to all interfaces by running `nmcli` or `ip -c a`.
   - Determine if you want to and can connect to an IP address using ethernet, bridge, WiFi, cellular, or StaticWire.
   - Show the host public key fingerprint for the ssh daemon on the CM4.
      - `ssh-keygen -lv -f /etc/ssh/ssh_host_ed25519_key.pub`
         - Doing this via the built in screen is secure since there should be no man in the middle attack.
   - Open a new terminal and connect via ssh
      - `ssh -o VisualHostKey=yes -i demo dc@IPAddress`
      - When prompted, compare the public key fingerprint of the CM4 with the one determine above.
   - Since we are now connected via ssh and don't need a direct connection anymore:
      - `exit` to log out of the CM4 on the keyboard.




### Time Zone Setup ###
- Check the current time zone.
   - `timedatectl`
- List all time zone options.
   - `timedatectl list-timezones`
- Set the time zone
   - `sudo timedatectl set-timezone America/New_York`




### CAN Bus Module Setup ###

- Setup device overlays
   - `sudo sh -c "echo 'dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=23' >> /boot/firmware/config.txt"`
   - `sudo sh -c "echo 'dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=24' >> /boot/firmware/config.txt"`

- Setup systemd-network
   - `sudo sh -c "echo '[Match]\nName=can0\n\n[CAN]\nBitRate=33300\n\n[Link]\nRequiredForOnline=no\n' > /etc/systemd/network/80-can0.network"`
   - `sudo sh -c "echo '[Match]\nName=can1\n\n[CAN]\nBitRate=500000\n\n[Link]\nRequiredForOnline=no\n' > /etc/systemd/network/80-can1.network"`



### Analog Input Setup ###

- Setup device overlay
   - `sudo sh -c "echo 'dtoverlay=spi1-1cs' >> /boot/firmware/config.txt"`



### RS-485 Port Setup ###

- Setup device overlay
   - `sudo sh -c "echo 'dtoverlay=uart5' >> /boot/firmware/config.txt"`



### NFC Module Setup ###

- Setup udev Rules
   - `sudo sh -c 'echo SUBSYSTEM==\"usb\", ACTION==\"add\", ATTRS{idVendor}==\"054c\", ATTRS{idProduct}==\"06c1\", GROUP=\"plugdev\" >> /etc/udev/rules.d/nfcdev.rules'`



### Allow GUI ###

- Allow user `dc` to run the X Server
   - `sudo sh -c "echo 'allowed_users=anybody\n' > /etc/X11/Xwrapper.config"`



## Python Module Setup ##

```
sudo reboot
```

Log back in

```
pip3 install git+https://github.com/AndySchroder/DistributedCharge
```



## Configure Distributed Charge ##

Setup the config directory and copy the sample configuration file into it.

```
cd
mkdir ~/.dc/
wget -P ~/.dc/ https://raw.githubusercontent.com/AndySchroder/DistributedCharge/master/SampleConfig/Config.yaml
```

Now edit the configuration file.

- `vi ~/.dc/Config.yaml`
   - Under the `Buyer` section input the [lndconnect URI](https://github.com/LN-Zap/lndconnect/blob/master/lnd_connect_uri.md) for your lnd node into the `LNDhost` field.
      - See also, https://github.com/AndySchroder/StaticWire?tab=readme-ov-file#autopay for more discussion.
   - Save and close the file. No other changes are needed. All other parameters are either reasonable defaults, values for a seller, or default values for the GRID implmentation of Distributed Charge that are not needed and are ignored.



Install the script as a systemd service:

- TODO

________________________________________________________________

# Copyright #

Copyright (c) 2025, [Andy Schroder](http://AndySchroder.com)
  
  
________________________________________________________________


# License #


Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
  
  
________________________________________________________________








