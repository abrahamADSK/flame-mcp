# Wiretap CLI Tools Reference (Flame 2026.2)

Command-line tools installed under `/opt/Autodesk/wiretap/tools/2026.2/`. These talk to the IFFFS server (default `127.0.0.1:IFFFS`) and expose the same object model as the Wiretap SDK from a shell. Use them for project creation, node traversal, metadata read/write, and frame-level I/O outside the Flame process.

Each section below is the `--help` output of one tool captured verbatim. Calling a tool with no arguments typically prints the same usage block.

## wiretap_can_create_node

```
Usage: wiretap_can_create_node [Options] <Params>

 Query if a node type can be created under node or not.
 Will print either 'can create' or 'can NOT create' in stdout.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -t|--node_type <node type>    Server-specific node type string
                                 (default = NODE)
  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

  # PROJECT node can be created under /projects node
  $ wiretap_can_create_node -n /projects -t PROJECT
  can create

  # PROJECT node cannot be created under / node
  $ wiretap_can_create_node -n / -t PROJECT
  can NOT create

SEE ALSO

 wiretap_create_node, wiretap_get_node_type, wiretap_get_children
```

## wiretap_client_tool

```
Usage: wiretap_client_tool [Options]

 Perform various operations on Wiretap servers.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -S|--storage_id <storage ID>  Storage ID
  -c|--src_clip <node ID>       Source clip node ID to copy
  -p|--parent_node <node ID>    Parent node ID for the new clip
  -k|--keep_node                Keep destination node (do not destroy)
  -N|--name <name>              Name of the new clip (default = NewClip)
  -t|--type <type>              Server-specific type of the new clip
                                 (default = CLIP)
  -n|--num_frames <num>         Number of frames in the source clip
  -r|--read_ahead <num>         Number of read-ahead frames
                                 (default = -1, use default strategy)
  -P|--params <file>            Parameters XML file
  -o|--output <file>            Destination frame output file
  -L|--latencies <file>         Frame latencies output file
  -m|--metadata_tag <tag>       Metadata tag for the new clip
  -M|--metadata <data>          Metadata for the new clip
  -C|--stay_connected           Stay connected until canceled (Ctrl+C)
  -l|--loop                     Loop until canceled (Ctrl+C)
  -T|--timeout <ms>             Ping timeout in milliseconds
                                 (default = 30000)
  --help                        Display this message and exit

EXAMPLE

  # Extract server information
  $ wiretap_client_tool
  Ping of host: '127.0.0.1:IFFFS' successful.
  Wiretap server daemon version is 2026.
  Wiretap node server version is 2026.0.0.48. [2026.0.0.48]
  Wiretap server name: vxfhost
  Wiretap server vendor is 'Autodesk'.
  Wiretap server product is 'IFFFS'.
  Wiretap server storage id is 'B1A7D8FE-C83A-4DE8-8771-AA853FE355DE-IFFFS'.
  Wiretap server host Name: vxfhost
  Wiretap server host OS: Linux
  Wiretap server host UUID is 'B1A7D8FE-C83A-4DE8-8771-AA853FE355DE'.
  Wiretap server node port: 7549
  Wiretap server frame port: 49152
  Wiretap server metadata IP 0: 10.183.43.223
  Wiretap server metadata IP 1: 192.168.2.10
  Wiretap server data IP 0: 10.183.43.223
  Wiretap server data IP 1: 192.168.2.10

SEE ALSO

 wiretap_ping, wiretap_network_tool, wiretap_rw_frame
```

## wiretap_create_audio

```
Usage: wiretap_create_audio [Options] <Params>

 Create an audio stream node under a parent node.

PARAMS

  -n|--node_id <node ID>        Parent clip node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -N|--num_samples <num>        Number of samples to create
                                 (default = 48000)
  -t|--node_type <type>         Server-specific node type
                                 (default = 'AUDIOSTREAM')
  -d|--display_name <name>      Display name
                                 (default = 'track')
  -c|--num_channels <num>       Number of channels
                                 (default = 1)
  -r|--sample_rate <rate>       Sample rate
                                 (default = 48000)
  -b|--bits_per_sample <bits>   Bits per sample
                                 (default = 16)
  -f|--format <format>          Format tag: wav, aiff, dlaudio_int16
                                 (default = dlaudio_int16)
  -M|--metadata_file <file>     Metadata file
                                 (default = none)
  -m|--metadata_tag <tag>       Metadata stream tag
                                 (default = none)
                                 Use wiretap_get_available_metadata to get
                                 list of available stream name for a given node.
  --help                        Display this message and exit

SEE ALSO

 wiretap_create_clip, wiretap_rw_file, wiretap_rw_frame
```

## wiretap_create_clip

```
Usage: wiretap_create_clip [Options] <Params>

 Create a new clip node under a parent node.

PARAMS

  -n|--node_id=<Node ID>        Parent Node Id

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -N|--nb_frames=<nb frames>    Number of frames to create
                                 (default = 1)
  -t|--node_type=<type>         Server-specific node type>
                                 (default = 'CLIP')
  -d|--display_name=<Name>      Display Name
                                 (default = node)
  -x|--width=<frame width>      Frame width
                                 (default = 720)
  -y|--height=<frame height>    Frame height
                                 (default = 486)
  -c|--nb_channels=<nb>         Number of channels
                                 (default = 3)
  -r|--rate=<rate>              Frame rate (default = 30)
  -b|--bits_per_pixel=<bpp>     Bits per pixel: 24, 30, 32, 36, 48
                                 (default = 24)
  -f|--format=<fmt>             Image format tag: rgb_le, rgb_float_le, dpx, sgi, etc>
                                 (default = rgb)
  -s|--scan_format=<fmt>        Scan format: field1_odd, field2_odd, field1_even, field2_even, progressive
  -p|--pixel_ratio=<ratio>      Pixel ratio
  -M|--metadata_file=<file>     Metadata file name
                                 (default = none)
  -m|--metadata_tag <tag>       Metadata stream tag
                                 (default = none)
                                 Use wiretap_get_available_metadata to get
                                 list of available stream name for a given node.
  -C|--colour_space=<cs>        Colour space
                                 (default = none)
  --help                        Display this message and exit

SEE ALSO

 wiretap_create_node, wiretap_get_clip_format, wiretap_rw_frame
```

## wiretap_create_node

```
Usage: wiretap_create_node [Options] <Params>

 Create a new node of a given type under a parent node.

PARAMS

  -n|--node_id <ID>             Parent Node ID>

OPTIONS

  -t|--node_type <type>         Server-specific node type
                                 (default = NODE)
  -d|--display_name <name>      New node display name
                                 (default = none)
  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -f|--metadata_file <file>     Metadata file name
                                 (default = none)
  -s|--metadata_tag <tag>       Metadata stream tag
                                 (default = XML)
                                 Use wiretap_get_available_metadata to get
                                 list of available stream name for a given node.
  -g|--group <group>            Effective group name
                                 (assumes super-user privileges)
  -u|--umask <umask>            Umask
                                 (default = parent process umask)
  -V|--requested_version <#[.#[.#Point]]>   (default = 2026.2.0)
     Server specific, the server might ignore the requested version.
     If specified and the client version is not available on the server,
     the version pointed to by the symlink 'current' will be used.
     If specified and the requested version is not available on the server,
     the call will fail.
  --help                        Display this message and exit

EXAMPLES

   # To create a new Flame Family project, you can use the following command:
   $ wiretap_create_node -h localhost:IFFFS -n /projects -t PROJECT -d MyProjectName

   # A specific version can be specified with -V parameter,
   # providing that the matching IFFFS wiretap server is installed.
   $ wiretap_create_node -h localhost:IFFFS -n /projects -t PROJECT -d MyProjectName -V 2026
   $ wiretap_create_node -h localhost:IFFFS -n /volumes/stonefs -t PROJECT -d MyProjectName -V 2025.1

   # To create a new Flame Family project with specific parameters, you can use the following command:
   $ wiretap_create_node -h localhost:IFFFS -n /projects -t PROJECT -d MyProjectName -f <file> -s XML

   # where <file> is an XML file with the settings of the project.
   #
   # See /opt/Autodesk/xml/2026.2/schema/wiretap/project.xsd for valid fields.
   # See https://help.autodesk.com/view/FLAME/2026/ENU/?guid=wiretap_ifffs_project_xml for mode details.

   # The tool will respect the current uid/gid/umask of the parent process.
   # This might not match the intended ownership of the project.
   # The group and umask can be changed with the --group/--umask
   $ wiretap_create_node -h localhost:IFFFS -n /projects -t PROJECT -d MyProjectName -f <file> -s XML --group=secondary --umask=077

SEE ALSO

 wiretap_destroy_node, wiretap_get_metadata, wiretap_set_metadata, wiretap_get_children
```

## wiretap_destroy_node

```
Usage: wiretap_destroy_node [Options] <Params>

 Destroy a specified node on the server.

PARAMS

  -n|--node_id <node ID>        Node ID to destroy

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

NOTES

 Some nodes will require to be empty in order to be destoyed, while others will
 remove the children upon destruction. This behavior is node/server specific.

SEE ALSO

 wiretap_create_node, wiretap_duplicate_node, wiretap_rename_node


EXAMPLES

   # Creates a new Flame Family project, and later destroy it:
   $ wiretap_create_node --node_id /projects/ --display_name MyProject --type PROJECT
   Created node '/projects/B75D42D7-CB31-4E1E-AF3F-6263FEEC1795'.
   $ wiretap_destroy_node --node_id /projects/B75D42D7-CB31-4E1E-AF3F-6263FEEC1795
   Destroyed node '/projects/B75D42D7-CB31-4E1E-AF3F-6263FEEC1795'.
```

## wiretap_duplicate_node

```
Usage: wiretap_duplicate_node [Options] <Params>

 Duplicate a node on the server.

PARAMS

  -n|--node_id <node ID>        Parent node ID
  -s|--source_node_id <node ID> Source node ID
  -d|--display_name <name>      Display name of the duplicate node

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

   # Browse a project hierarchy to find a library and duplicate it

   # Find project node

   $ wiretap_print_tree -n /projects -d 1
   Server: 'vxfHost' Wiretap Version: 2026  Server Vendor: Autodesk  Product: IFFFS  Version: 2026
   Printing Wiretap Tree

   projects <node> (PROJECTS) Node ID: /projects
       MyProject <node> (PROJECT) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149

   # Find workspace node

   $ wiretap_print_tree -n /projects/d3b97e07-7063-4b15-9906-221feca18149 -d 1
   Server: 'vxfhost' Wiretap Version: 2026  Server Vendor: Autodesk  Product: IFFFS  Version: 2026
   Printing Wiretap Tree

   MyProject <node> (PROJECT) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149
       Workspace <node> (WORKSPACE) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8
       Shared Libraries <node> (LIBRARY_LIST) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005cd87f_67fd60da_000804a6

   # Find Libraries node

   $ wiretap_print_tree -n /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8 -d 1
   Server: 'vxfhost' Wiretap Version: 2026.1  Server Vendor: Autodesk  Product: IFFFS  Version: 2026.1
   Printing Wiretap Tree

   Workspace <node> (WORKSPACE) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8
       Desktop <node> (DESKTOP) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60f0_000050b6
       Libraries <node> (LIBRARY_LIST) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac

   # Find Library node

   $ wiretap_print_tree -n /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac -d 1
   Server: 'vxfhost' Wiretap Version: 2026.1  Server Vendor: Autodesk  Product: IFFFS  Version: 2026.1
   Printing Wiretap Tree

   Libraries <node> (LIBRARY_LIST) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac
       Default Library <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_000050a9
       Grabbed References <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_0000512a
       Timeline FX <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_00005139

   # Duplicate it

   $ wiretap_duplicate_node --node_id /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac --source_node_id /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_000050a9 --display_name "Duplicated Library"
   Created node '/projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/006d6f7f_67fd6166_00027ddc'.

   $ wiretap_print_tree -n /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac -d 1
   Server: 'vxfhost' Wiretap Version: 2026.1  Server Vendor: Autodesk  Product: IFFFS  Version: 2026.1
   Printing Wiretap Tree

   Libraries <node> (LIBRARY_LIST) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac
       Default Library <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_000050a9
       Grabbed References <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_0000512a
       Timeline FX <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/005d9a7f_67fd60f0_00005139
       Duplicated Library <node> (LIBRARY) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149/005d9a7f_67fd60ed_000e79a8/005d9a7f_67fd60ed_000e79ac/006d6f7f_67fd6166_00027ddc

SEE ALSO

 wiretap_create_node, wiretap_destroy_node, wiretap_rename_node
```

## wiretap_event_listener

```
Usage: wiretap_event_listener [Options] <Params>

 Listen for events on a given node.

PARAMS

  -n|--node_id <node ID>        Node ID
                                 (can be specified multiple times)

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -d|--dump_details             Dump serialized event details
  -s|--metadata_tag <tag>       Metadata stream tag
                                 (default = XML)
  -f|--file <file>              File containing metadata
                                 (default = none)
  --help                        Display this message and exit
```

## wiretap_get_available_metadata

```
Usage: wiretap_get_available_metadata [Options] <Params>

 Retrieve the list of available metadata stream formats usable with a given node id.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

   # Print the list of available metadata streams on a PROJECT node.

   $ wiretap_get_available_metadata -n /projects/d3b97e07-7063-4b15-9906-221feca18149
   ProjectLocator
   XML
   Commit

SEE ALSO

 wiretap_is_metadata_available, wiretap_get_metadata, wiretap_set_metadata
```

## wiretap_get_children

```
Usage: wiretap_get_children [Options] <Params>

 Retrieve the children of a given node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -d|--delimiter <char>         Delimiter character
                                 (default = none)
  -s|--separator <char>         Separator character
                                 (default = newline)
  -N|--show_display_names       Show display names instead of node IDs
  --help                        Display this message and exit

EXAMPLES

   # List projects node and display name from a IFFFS Wiretap server:

   $ wiretap_get_children --node_id /projects
   /projects/d3b97e07-7063-4b15-9906-221feca18149

   $ wiretap_get_children --node_id /projects --show_display_names
   MyProject

   # List projects names in comma separated list, where each name is surrounded by quotes::

   $ /opt/Autodesk/wiretap/tools/current/wiretap_get_children -show_display_names -node_id /projects/ -s, -d\"
   "My Other Project","MyProject"

SEE ALSO

 wiretap_get_root_node, wiretap_get_parent_node, wiretap_print_tree
```

## wiretap_get_clip_format

```
Usage: wiretap_get_clip_format [Options] <Params>

 Retrieve the format of a given clip node.

PARAMS

  -n|--node_id <node ID>        Node ID of the clip

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

  # Retrieve the format of a Flame Family project clip node:
  $ wiretap_get_clip_format --node_id /projects/MyProject/1013507f_6808d3c8_00098138/1013507f_6808d3cd_00070d4a/1013507f_6808d3cd_00070d64/1013507f_6808d3cd_00070d78/3027267f_680b8476_000844b5
  Format rgb
  Width 1920
  Height 1080
  BitsPerPixel 24
  BitsPerChannel 8
  Channels 3
  BufferSize 6220816
  PixelRatio 1
  FrameRate 23.976
  ScanFormat progressive
  ColourSpace raw
  MetaDataTag XML
  MetaDataStream <XML Version="1.0"><ClipData><TapeName>COLOUR</TapeName><ClipCreationDate>Fri Apr 25 08:47:50 2025</ClipCreationDate><ClipCreationDateSec>1745585270</ClipCreationDateSec><ClipModificationTime>1745585270</ClipModificationTime><DropMode>NDF</DropMode><SrcTimecode>00:00:00+00</SrcTimecode><Duration>00:00:00+05</Duration><ProxyFormat>none</ProxyFormat></ClipData></XML>

SEE ALSO

 wiretap_get_node_type, wiretap_get_frames, wiretap_rw_frame
```

## wiretap_get_display_name

```
Usage: wiretap_get_display_name [Options] <Params>

 Retrieve the display name of a given node ID.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

   # Fetch project name on a IFFFS Wiretap server:
   $ wiretap_get_display_name --node_id /projects/d3b97e07-7063-4b15-9906-221feca18149
   MyProject

SEE ALSO

 wiretap_get_node_type, wiretap_get_children, wiretap_get_parent_node
```

## wiretap_get_frames

```
Usage: wiretap_get_frames [Options] <Params>

 Retrieve frame IDs or paths for a given node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -d|--delimiter <char>         Delimiter character
                                 (default = none)
  -s|--separator <char>         Separator character
                                 (default = newline)
  -p|--print_paths              Print frame file paths instead of IDs
  --help                        Display this message and exit

EXAMPLES

  # List all frame IDs for a given node:
  $ wiretap_get_frames --node_id /projects/MyProject/1013507f_6808d3c8_00098138/1013507f_6808d3cd_00070d4a/1013507f_6808d3cd_00070d64/1013507f_6808d3cd_00070d78/3027267f_680b8476_000844b5
  0x000000000000000a@453d8012-6cc0-422f-b008-05be729119f2
  0x000000000000000b@453d8012-6cc0-422f-b008-05be729119f2
  0x000000000000000c@453d8012-6cc0-422f-b008-05be729119f2
  0x000000000000000d@453d8012-6cc0-422f-b008-05be729119f2
  0x000000000000000e@453d8012-6cc0-422f-b008-05be729119f2

  # List all frame paths for a given node:
  $ wiretap_get_frames --print_paths --node_id /projects/MyProject/1013507f_6808d3c8_00098138/1013507f_6808d3cd_00070d4a/1013507f_6808d3cd_00070d64/1013507f_6808d3cd_00070d78/3027267f_680b8476_000844b5
  /var/opt/Autodesk/flame/projects/MyProject/media/0/0x000000000000000a.dpx
  /var/opt/Autodesk/flame/projects/MyProject/media/0/0x000000000000000b.dpx
  /var/opt/Autodesk/flame/projects/MyProject/media/0/0x000000000000000c.dpx
  /var/opt/Autodesk/flame/projects/MyProject/media/0/0x000000000000000d.dpx
  /var/opt/Autodesk/flame/projects/MyProject/media/0/0x000000000000000e.dpx

  # List all frame paths for a given node in a comma separated list:
  $ wiretap_get_frames --print_paths -d\" -s, --node_id /projects/MyProject/1013507f_6808d3c8_00098138/1013507f_6808d3cd_00070d4a/1013507f_6808d3cd_00070d64/1013507f_6808d3cd_00070d78/3027267f_680b8476_000844b5
  "/var/opt/Autodesk/flame/projects/allo/media/0/0x000000000000000a.dpx","/var/opt/Autodesk/flame/projects/allo/media/0/0x000000000000000b.dpx","/var/opt/Autodesk/flame/projects/allo/media/0/0x000000000000000c.dpx","/var/opt/Autodesk/flame/projects/allo/media/0/0x000000000000000d.dpx","/var/opt/Autodesk/flame/projects/allo/media/0/0x000000000000000e.dpx"

SEE ALSO

 wiretap_get_num_frames, wiretap_rw_frame, wiretap_rw_file
```

## wiretap_get_metadata

```
Usage: wiretap_get_metadata [Options] <Params>

 Fetch given metadata stream from specific node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -m|--metadata_tag <tagm>      Metadata stream tag
                                 (Default = BLOB)
                                 Use wiretap_get_available_metadata to get
                                 list of available stream name for a given node.
  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -f|--filter <filter>          Metadata filter
                                 Depend on node type. Rarely used.
  -d|--depth <depth>            Depth
                                 (default = 1)
  -t|--timeout <ms>             Timeout in milliseconds
  -o|--output <file>            Output file
                                 (default = stdout)
  --help                        Display this message and exit

EXAMPLES

    # Get Project metadata from IFFFS server
    $ /wiretap_get_metadata --host 127.0.0.1:IFFFS --node_id /projects/project_name --metadata_tag xml --output /tmp/info

    # Get Clip metadata from Wiretap Gateway server
    $ wiretap_get_children -h localhost:Gateway -n /mnt/storage/NOISE.00000000.dpx@CLIP(H7)ImageIO
    # Be sure to enclose node ids in quotes to avoid shell expansion
    # of some characters like () present in node ids.
    $ wiretap_get_metadata --host 127.0.0.1:Gateway --node_id "/mnt/storage/NOISE.00000000.dpx@CLIP(H7)ImageIO" --metadata_tag SourceData --output /tmp/info

    # Possible metadata stream can be queried for a given node using
    # wiretap_get_available_metadata
    $ wiretap_get_available_metadata --host 127.0.0.1:IFFFS --node_id /projects/project_name

SEE ALSO

 wiretap_create_node, wiretap_set_metadata, wiretap_get_children
```

## wiretap_get_node_type

```
Usage: wiretap_get_node_type [Options] <Params>

 Retrieve the type of a given node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_is_clip, wiretap_get_display_name, wiretap_get_children
```

## wiretap_get_num_frames

```
Usage: wiretap_get_num_frames [Options] <Params>

 Retrieve the number of frames for a given node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_set_num_frames, wiretap_get_frames, wiretap_rw_frame
```

## wiretap_get_parent_node

```
Usage: wiretap_get_parent_node [Options] <Params>

 Retrieve the parent node of a given node.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_get_root_node, wiretap_get_children, wiretap_print_tree
```

## wiretap_get_root_node

```
Usage: wiretap_get_root_node [Options]

 Retrieve the root node of a given server.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_get_parent_node, wiretap_get_children, wiretap_print_tree
```

## wiretap_get_storage_id

```
Usage: wiretap_get_storage_id [Options] 

 Fetch the storage ID from a server.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_resolve_storage_id, wiretap_ping, wiretap_network_tool
```

## wiretap_ip_resolver

```
Usage: wiretap_ip_resolver [Options]

 Resolve the storage ID of a given server ID.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -S|--storage_id <storage ID>  Storage ID
  -l|--loop                     Loop until canceled (Ctrl+C)
  --help                        Display this message and exit

SEE ALSO

 wiretap_resolve_storage_id, wiretap_ping
```

## wiretap_is_clip

```
Usage: wiretap_is_clip [Options] <Params>

 Query if a node is a clip node or not.
 Will print 0 or 1 on stdout to return results.

PARAMS

  -n|--node_id <node ID>        Node ID

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_get_node_type, wiretap_get_num_frames, wiretap_get_frames
```

## wiretap_is_metadata_available

```
Usage: wiretap_is_metadata_available [Options] <Params>

 Query if a metadata stream ID is usable with a given node ID.

PARAMS

  -n|--node_id <node ID>        Node ID
  -m|--metadata_tag <tag>       Metadata stream tag

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_get_available_metadata, wiretap_get_metadata, wiretap_set_metadata
```

## wiretap_multicast_listener

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_multicast_listener', '--help']' timed out after 5 seconds]
```

## wiretap_network_tool

```
Usage: wiretap_network_tool [Options]

 Use self-discovery to identify and contact all Wiretap servers
 on the network. Users can forcibly remove dead servers from the
 list.

OPTIONS

  -g|--gateway <IP[:Port]>     IP/hostname and port of server to retrieve
                                the initial server list from. Will rely on
                                the first server responding to multicast if
                                not specified.
  -h|--help                    Display this message and exit.

EXAMPLES

    # Discover all Wiretap servers on the network
    $ wiretap_network_tool

    # Retrieve the server list from a specific gateway
    $ wiretap_network_tool --gateway 192.168.1.1:7555

SEE ALSO

 wiretap_client_tool, wiretap_ping
```

## wiretap_ping

```
Usage: wiretap_ping [Options]

Ping a Wiretap server to check its availability.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -s|--storage_id <ID>          Storage ID
  -t|--timeout <ms>             Timeout in milliseconds
                                 (default = 30000)
  -r|--retries <num>            Number of retries
                                 (default = 0)
  -d|--delay <ms>               Delay between retries in milliseconds
                                 (default = 0)
  --help                        Display this message and exit

NOTES

    IP address: IPv4 address in the form of ###.###.###.###
    Host name:  Any network resolvable host name.
                If 'ping hostname' does not work, wiretap_ping won't work either.
    Port:       TCP node port of the service.
    Database:   Wiretap Database type (IFFFS, Backburner, Gateway).

    Storage ID: A persistent identifier that can be used to find a
                specific server instance on a specific machine,
                and is guaranteed to be constant no matter the network
                configuration.


  In certain scenarios, Wiretap uses self-discovery to resolve the
  server ID provided by users in command line tools. This procedure
  is typically carried out when the ID lacks sufficient information
  to establish a connection.

  When using the format `<ip>:<port>`, self-discovery is bypassed as
  this provides adequate information to establish the connection.
  This method is the quickest and most reliable one, but offers the
  least flexibility.

  If you use `<hostname>:<port>` instead of an IP address, a name
  resolution will be performed via DNS. In some network configurations,
  this name resolution may take a considerable amount of time to fail,
  causing apparent hangs in clients.

  When using "IFFFS", "Backburner", or "Gateway" as a replacement
  for a port number, or when a Storage ID is used, the client resorts to
  self-discovery to locate the port. This process includes sending a
  multicast discovery request and awaiting a response from the Wiretap
  servers. Since multicast messages are inherently a best-effort
  mechanism, it's possible for any network component to drop these
  messages. To expedite the procedure, the client retrieves the
  complete list from the first server that answers the discovery
  request. In most scenarios, this will be a local Wiretap server
  due to proximity.

EXAMPLES

  Ping local host IFFFS wiretap server:
    wiretap_ping --host localhost:IFFFS

  Ping local host Backburner Manager directly:
    wiretap_ping --host localhost:7347

  Ping remote Wiretap Gateway server:
    wiretap_ping --host remoteHost.my.domain.com:Gateway

  Ping using storage ID:
    wiretap_ping --storage_id B1A7D8FE-C83A-4DE8-8771-AA853FE355DE-IFFFS

SEE ALSO
 wiretap_network_tool, wiretap_resolve_storage_id, wiretap_ip_resolver
```

## wiretap_print_tree

```
Usage: wiretap_print_tree [Options]

 Print the tree structure of a Wiretap server.

OPTIONS

  -n|--node_id <node ID>        Start from node ID
  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -m|--metadata_tag <tag>       Show metadata of specified tag
  -d|--depth <depth>            Maximum depth to descend (default = 2)
  -v|--verbose                  Enable verbose output
  -k|--keep_going               Keep going on error
  --help                        Display this message and exit

EXAMPLES

   # Print projects name and IDs on a IFFFS wiretap server
   $ wiretap_print_tree --node_id /projects -d 1
   Server: 'vxfhost' Wiretap Version: 2026  Server Vendor: Autodesk  Product: IFFFS  Version: 2026
   Printing Wiretap Tree

   projects <node> (PROJECTS) Node ID: /projects
       MyOtherProject <node> (PROJECT) Node ID: /projects/2453a5d4-4aaf-44c4-abec-7954e3df5edd
       MyProject <node> (PROJECT) Node ID: /projects/d3b97e07-7063-4b15-9906-221feca18149

SEE ALSO

  wiretap_get_children, wiretap_get_root_node, wiretap_get_parent_node
```

## wiretap_read_stream

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_read_stream', '--help']' timed out after 5 seconds]
```

## wiretap_remove_server

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_remove_server', '--help']' timed out after 5 seconds]
```

## wiretap_rename_node

```
Usage: wiretap_rename_node [Options] <Params>

 Rename a node on the server.

PARAMS

  -n|--node_id <node ID>        Node ID to rename
  -d|--display_name <name>      New display name for the node

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

SEE ALSO

 wiretap_create_node, wiretap_destroy_node, wiretap_duplicate_node

Node ID not specified.
```

## wiretap_resolve_path

```
Usage: wiretap_resolve_path [Options] <Params>

 Resolve a display path to a node ID.

PARAMS

  -p|--path <path>              Display path to resolve

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  --help                        Display this message and exit

EXAMPLES

  # Resolve a path to a reel on desktop of a Flame Flamily project:
  $ wiretap_resolve_path --path "/projects/MyProject/Workspace/Desktop/Reels/Reel 1"
  Path successfully resolved to node ID: '/projects/.../1013507f_6808d3cd_00070d71'

NOTE

 Since display names are not unique, if duplicate elements on the same level
 have the same display name, the wrong element might be returned.

SEE ALSO

 wiretap_get_root_node, wiretap_get_parent_node, wiretap_get_children

Path not specified.
```

## wiretap_resolve_storage_id

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_resolve_storage_id', '--help']' timed out after 5 seconds]
```

## wiretap_rw_file

```
Usage: wiretap_rw_file [Options] <Params>

 Read a local file and send content to a data stream or
 Read a data stream and write it to a local file.

PARAMS

  -l|--file <file>              Local file path.
  -s|--stream_id <stream id>    Data stream ID.

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1:IFFFS)
  -w|--write                    Write to server.
                                 (default = read from server)
  --help                        Display this message and exit

SEE ALSO

  wiretap_rw_frame, wiretap_read_stream, wiretap_write_stream
```

## wiretap_rw_frame

```
Usage: wiretap_rw_frame [Options] <Params>

 Read or write frames from/to a clip node.

PARAMS

  -n|--node_id <node ID>[,...]  Clip node IDs

OPTIONS

  -h|--host <host>[:DB/Port]    Host name or IP address
                                 optionally Database or Port
                                 (default = 127.0.0.1)
  -f|--file <file>              Frame file path
                                 (default = ./frame_#.format)
  -s|--skip_file_io             Skip file IO
                                 (default = false)
  -i|--frame_index <index>      Zero-based frame index, -1 for all frames
                                 (default = 0)
  -w|--write                    Write frame
                                 (default = read)
  -r|--disable_read_ahead       Disable read ahead
                                 (default = enabled)
  --help                        Display this message and exit

EXAMPLES

  # Read a frame from a clip node
  $ wiretap_rw_frame --node_id /path/to/clip --frame_index 0

  # Write a frame to a clip node
  $ wiretap_rw_frame --node_id /path/to/clip --file frame.raw --write

SEE ALSO

  wiretap_rw_file, wiretap_read_stream, wiretap_write_stream

Node ID not specified.
```

## wiretap_server_dump

```
Usage: wiretap_server_dump [Options]

 Dump information about Wiretap servers.

OPTIONS

  -v|--version                 Display protocol version
  -p|--ports                   Display ports
  -U|--uuids                   Display host UUIDs
  -F|--full                    Display full server information
  -t|--timeout <time>          Time to wait for replies
                                (default = 0s)
  -g|--gateway <IP>[:<port>]   Use specific server to fetch list.
                                (default use multicast)
  -d|--database_filter <db>    Database filter
                                (default = none)
  --help                       Display this message and exit

SEE ALSO

 wiretap_services_snapshot, wiretap_network_tool, wiretap_ping
```

## wiretap_services_snapshot

```
Usage: /opt/Autodesk/wiretap/tools/2026.2/wiretap_services_snapshot [-p <port>|...] [-f <output> ] [<hostname>|...] [-h]

  Extract information for wiretap servers running on a given host and save
  them either in /opt/Autodesk/cfg/services.cfg or a specified file.

 <hostname>     : Specify one or many hostname/ip to query.
                  Localhost used if none defined.
 -p <port>      : Specify a port to query. Can be used multiple times.
                  Default:
                     7549 - IFFFS Wiretap Server
                     7347 - Backburner
                     7183 - Wiretap Gateway
 -f <output>    : Output file name or stdout
                  Default: /opt/Autodesk/cfg/services.cfg
```

## wiretap_set_metadata

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_set_metadata', '--help']' timed out after 5 seconds]
```

## wiretap_set_num_frames

```
[--help failed: Command '['/opt/Autodesk/wiretap/tools/2026.2/wiretap_set_num_frames', '--help']' timed out after 5 seconds]
```
