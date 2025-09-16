# MeshBBS

Minimalistic Meshtastic Bulletin Board System written in python!

Stores data and config in single json file.

## Features

* Users can leave bulletins for others to read
* Users see new bulletins left by others
* Users can see some stats from the BBS
* Users can page the sysop (send them a message)
* Sysop can delete bulletins. Users can delete their own bulletins.

Yes, it's quite minimalistic.

## Running

* cp bbs.json.example bbs.json
* Edit bbs.json to suit your needs.
* Install the meshtastic library in venv or whatever you like
* Run the bbs

## Future

* Some kind of plugin API (doors) to add additional functionality
* Better documentation
