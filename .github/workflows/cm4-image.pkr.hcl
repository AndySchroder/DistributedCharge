variable "release_version" {
  type    = string
  default = "dev"
}

source "arm" "cm4" {
  file_urls             = ["http://cdimage.ubuntu.com/releases/22.04.4/release/ubuntu-22.04.4-preinstalled-server-arm64+raspi.img.xz"]
  file_checksum_url     = "http://cdimage.ubuntu.com/releases/22.04.4/release/SHA256SUMS"
  file_checksum_type    = "sha256"
  file_target_extension = "xz"
  file_unarchive_cmd    = ["unxz", "$ARCHIVE_PATH"]
  image_path            = "output/cm4-custom-image-${var.release_version}.img"
  image_size            = "3G"
  image_type            = "dos"
  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = "2048"
    filesystem   = "vfat"
    size         = "256M"
    mountpoint   = "/boot/firmware"
  }
  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = "526336"
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }
  qemu_binary_source_path = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path = "/usr/bin/qemu-aarch64-static"
}

build {
  sources = ["source.arm.cm4"]

  provisioner "shell" {
    inline = [
      "apt-get update",
      "apt-get install -y x11-xserver-utils xterm xinit vim git jq python3-pip build-essential cmake g++ libpcsclite-dev libcurl4-openssl-dev python3-pip libmbim-utils network-manager can-utils python3-tk python3-zmq",
      "pip3 install python-can cantools can-isotp pillow pydbus gpiozero RPi.GPIO",
      "pip3 install git+https://github.com/AndySchroder/RPi_mcp3008",
      "pip3 install git+https://github.com/AndySchroder/helpers2",
      "pip3 install git+https://github.com/AndySchroder/lnd-grpc-client.git",
      "mkdir -p /home/ubuntu/Desktop",
      "git clone https://github.com/joshwardell/model3dbc /home/ubuntu/Desktop/model3dbc",
      "cd /home/ubuntu/Desktop/model3dbc && git reset --hard 7ec978ca618f13be375f0be9b2f25c19da500d3f",
      "git clone https://github.com/AndySchroder/DistributedCharge /home/ubuntu/Desktop/DistributedCharge",
      "echo 'dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=23' >> /boot/firmware/config.txt",
      "echo 'dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=24' >> /boot/firmware/config.txt",
      "echo 'dtoverlay=spi1-1cs' >> /boot/firmware/config.txt",
      "echo '[Match]\nName=can0\n\n[CAN]\nBitRate=33300\n\n[Link]\nRequiredForOnline=no\n' > /etc/systemd/network/80-can0.network",
      "echo '[Match]\nName=can1\n\n[CAN]\nBitRate=500000\n\n[Link]\nRequiredForOnline=no\n' > /etc/systemd/network/80-can1.network",
      "mkdir -p /home/ubuntu/.dc",
      "cp /home/ubuntu/Desktop/DistributedCharge/SampleConfig/Config.yaml /home/ubuntu/.dc/",
      "echo '@reboot xinit /home/ubuntu/Desktop/DistributedCharge/Launcher-car' | crontab -",
      "sed -i -e 's/allowed_users=console/allowed_users=anybody/g' /etc/X11/Xwrapper.config",
      "echo '${var.release_version}' > /etc/cm4-image-version"
    ]
  }
}