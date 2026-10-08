# Raspberry Pi SD-card backup and clone

PixEagle includes a Linux-only, offline SD workflow for making a private board
snapshot and cloning it to another card. It creates a raw image, verifies its
checksum, makes a separate PiShrink copy, compresses that copy, and verifies a
restore by reading the written bytes back. It never overwrites the raw image.

The entry point is:

```bash
cd ~/PixEagle
tools/pixeagle-sd.sh list
```

Install the host tools once on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y parted gzip pigz xz-utils udev e2fsprogs util-linux
```

## Back up a card

Shut down the Pi cleanly and remove its SD card. Insert it into the reader,
close file-manager windows that opened its partitions, and use a different
filesystem for the output. Keep at least three times the card capacity free:

```bash
tools/pixeagle-sd.sh backup ~/Pi-images/pixeagle-$(date +%Y%m%d-%H%M%S)
```

The command lists whole disks and marks internal disks as protected. Type the
complete removable device path, review the model and serial, then type
`BACKUP`. It unmounts only the selected card, refuses protected mounts and
device identity changes, and preserves the raw image if a later compression
step fails. The first run downloads the pinned PiShrink commit and verifies its
SHA-256 before executing it. The output contains `MANIFEST.json`, raw and
shrunk `.img` files, `.sha256` sidecars and an `.img.xz` archive.

Verify an archive without writing a card:

```bash
tools/pixeagle-sd.sh verify ~/Pi-images/pixeagle-*/pixeagle-full-shrunk.img.xz
sha256sum -c ~/Pi-images/pixeagle-*/pixeagle-full-shrunk.img.xz.sha256
```

The image contains credentials, keys, logs, model state and network settings.
Store it encrypted and keep it out of public repositories. It is a private
installation snapshot, not a factory image or a release artifact.

## Clone a card

Insert a destination card and confirm it is the intended removable device:

```bash
tools/pixeagle-sd.sh restore \
  ~/Pi-images/pixeagle-*/pixeagle-full-shrunk.img.xz
```

The command checks the archive checksum and decompressed size before listing the
destination. It refuses a card that is too small, asks for the exact
`ERASE /dev/sdX` confirmation, unmounts it, writes the image, and verifies the
bytes read back. Eject the reader before booting the clone. Do not boot the
original and clone together until hostname, SSH host identity, credentials and
any fixed network identity have been changed.

To resume a raw image that was created but not shrunk:

```bash
tools/pixeagle-sd.sh shrink ~/Pi-images/pending/pixeagle-full.img
```

The wrapper uses only the Python standard library and the pinned PiShrink
script. Raspberry Pi Imager can also restore the verified `.img` file; select
the image, select the destination card, and verify the destination before
writing. The workflow does not claim that a cloned board is safe for flight;
repeat the board-specific service, network, camera, Pixhawk and command-blocked
acceptance checks.
