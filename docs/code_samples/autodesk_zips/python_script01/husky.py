#!/usr/bin/env python
#*****************************************************************************/
#
# Filename: husky.py
#
# Copyright (c) 2015 Autodesk Canada Co.
# All rights reserved.
#
# This computer source code and related instructions and comments are the
# unpublished confidential and proprietary information of Autodesk, Inc.
# and are protected under applicable copyright and trade secret law.
# They may not be disclosed to, copied or used by any third party without
# the prior written consent of Autodesk, Inc.
#*****************************************************************************/
#
# Author: Jean-Francois Bouchard
#         Mathieu Sansregret
# Description : husky.py is a watchdog script looking at a specific folder for
#               modification, and then creates .clip files automatically.
#
# History: v1.0 - March 24th 2015
#
# Notes: for Apple notifications to work properly. please type the 2 follosing
#        commands in the mac terminal:
#
#        sudo easy_install pip
#        pip install pync
#

import xml.dom.minidom as minidom
import optparse
import sys
import os
import re
import shutil
import time

class bcolors:
    _NORM = chr(27) + '[0m'
    _GREEN = chr(27) + '[32m'
    _DGREEN = chr(27) + '[32m'
    _YELLOW = chr(27) + '[33m'
    _ORANGE = chr(27) + '[33m'
    _RED = chr(27) + '[31m'
    _BLACK = chr(27) + '[40m'


sleepy = 2     #seconds in between checks

print bcolors._NORM


#-------------------------------------------------------------------------------
#
#
def addFeed(feed,vuid,targetMIO,trackUID):

        tracks = targetMIO.getElementsByTagName('track')
        newID  = vuid

        #Iterate through the tracks, looking for perfect matches for the incoming feed
        for i in range(len(tracks)):
                if tracks[i].attributes["uid"].value == trackUID:

                        if ( len(vuid) == 0 ):
                                #Get the version of the last feed
                                allfeeds = tracks[i].getElementsByTagName('feed')
                                for j in range(len(allfeeds)):
                                        feedID = allfeeds[j].attributes["uid"].value
                                        if feedID == "v0":
                                                newID = "002"
                                        else:
                                                match = re.search( "([\d]+)", feedID)
                                                if match:
                                                        number = int(match.group(1))
                                                        number = number + 1
                                                        newID = "%03d" % number
                                                else:
                                                        print "Invalid feed uid in masterfile: %s" % feedID
                                                        sys.exit(2)

                        feed.attributes['vuid'].value = newID
                        feed.attributes['uid'].value = newID

                        #When the feed's track matches the one in the clip, add the feed to this track
                        tracks[i].getElementsByTagName('feeds')[0].appendChild(feed)


        return newID

#-------------------------------------------------------------------------------
#
#
def splice( masterFile, newFile , relPath):


        #Read the Gateway Clip XML files for the existing and new versions
        sourceGWXML     = minidom.parse(masterFile)
        newGWXML        = minidom.parse(newFile)

        #Get all of the tracks from the new
        allTracks       = newGWXML.getElementsByTagName('track')

        newVersionID = ''

        for i in range(len(allTracks)):
                theTrackID      = allTracks[i].attributes["uid"].value
                theTrack        = allTracks[i]
                theFeed = theTrack.getElementsByTagName('feed')[0]
                newVersionID = addFeed(theFeed,newVersionID,sourceGWXML,theTrackID)


        #Add a version description at the end of the file, for this new version
        doc             = minidom.Document()
        newVersion      = sourceGWXML.getElementsByTagName('versions')[0].appendChild(doc.createElement('version'))
        newVersion.setAttribute('type', 'version')
        newVersion.setAttribute('uid', newVersionID)

        name = doc.createElement('name')
        nameValue = doc.createTextNode(relPath)
        name.appendChild(nameValue)
        newVersion.appendChild(name)

        creationDate = doc.createElement('creationDate')
        currentDateTime = time.strftime("%c")
        dateTimeValue = doc.createTextNode(currentDateTime) 
        creationDate.appendChild(dateTimeValue)
        newVersion.appendChild(creationDate)

        resultXML       = sourceGWXML.toxml()

        # Create a backup of the original file
        bakfile = "%s.bak" % masterFile
        if not os.path.isfile(bakfile):
                shutil.copy2(masterFile,bakfile)
        else:
                created = False
                for i in range ( 1, 99 ):
                        bakfile = "%s.bak.%02d" % ( masterFile, i )
                        if not os.path.isfile(bakfile):
                                shutil.copy2(masterFile,bakfile)
                                created = True
                                break
                if not created:
                        bakfile = "%s.bak.last" % masterFile
                        shutil.copy2(masterFile,bakfile)



        outFile = masterFile

        print " Adding feed version %s" % newVersionID
        f = open(outFile, "w")
        f.write( resultXML )
        f.close()


#-------------------------------------------------------------------------------
#
#
def createClip(newDir,clipFile,relPath):
   getMediaScript = "/usr/discreet/mio/current/dl_get_media_info"

   if not os.path.isfile(getMediaScript):
           print "The get media info script is not installed: file %s missing" % getMediaScript
           sys.exit(2)


   if not os.path.isfile(clipFile):
           # create it
           initialpath = os.path.abspath(newDir)
           print " creating file with folder %s" % initialpath

           res = os.popen4("%s -r %s" % ( getMediaScript, initialpath ) )[1].readlines()

           f = open(clipFile, "w")
           for line in res:
                   f.write( line )
           f.close()
           addFirstMetadata(clipFile, relPath)
           return   


   tmpfile = "tmpfile"


   apath = os.path.abspath(newDir)
   print " Adding folder %s" % apath
   #output a temp file
   if os.path.isfile(tmpfile):
      os.remove(tmpfile)
   res = os.popen4("%s -r %s" % ( getMediaScript, apath ) )[1].readlines()

   f = open(tmpfile, "w")
   for line in res:
      f.write( line )
   f.close()
   splice(clipFile,tmpfile,relPath)

   if os.path.isfile(tmpfile):
           os.remove(tmpfile)



#-------------------------------------------------------------------------------
#
#
def addFirstMetadata(clipFile, relPath):


        #Read the Gateway Clip XML files for the existing and new versions
        sourceGWXML     = minidom.parse(clipFile)
#        newGWXML        = minidom.parse(newFile)

        #Add a version description at the end of the file, for this new version
        doc             = minidom.Document()
        versions        = sourceGWXML.getElementsByTagName('versions')[0]
        
        version         = versions.getElementsByTagName('version')[0]
        name = doc.createElement('name')
        nameValue = doc.createTextNode(relPath)
        name.appendChild(nameValue)
        version.appendChild(name)

        creationDate = doc.createElement('creationDate')
        currentDateTime = time.strftime("%c")
        dateTimeValue = doc.createTextNode(currentDateTime)
        creationDate.appendChild(dateTimeValue)
        version.appendChild(creationDate)

        resultXML       = sourceGWXML.toxml()

        f = open(clipFile, "w")
        f.write( resultXML )
        f.close()

#-------------------------------------------------------------------------------
#
#
def ccmenu():
   os.system('clear')
   print ""
   print "###### createClip.py Watchdog ######"
   print ""
   print "Type the path where the versions folders will be contained?:"
   folder = raw_input("->   ")
   while folder == "":
       folder = raw_input("->   ")
   if os.path.exists(folder) is False:
       print "Path not existing, will be created"
       print ""
       os.system("mkdir -p " + folder)
       os.system("chmod 777 " + folder)
   CMD = "echo " + folder + " | rev | cut -d '/' -f1 | rev"
   clipFileName = os.popen(CMD).read().rstrip('\n')
   if clipFileName is "":
       CMD = "echo " + folder + " | rev | cut -d '/' -f2 | rev"
       clipFileName = os.popen(CMD).read().rstrip('\n')
   clipFile = folder + "/" + clipFileName + ".clip"
   os.system('clear')
   print ""
   print "Folder " + bcolors._YELLOW + "[" + folder + "]" + bcolors._NORM + " will be watched"
   print ""
   diffdir(folder,clipFile)

#-------------------------------------------------------------------------------
#
#
def diffdir(folder,clipFile):
    dirList1 = [x[0] for x in os.walk(folder)]
    dirList2 = dirList1
    while len(list(set(dirList2) - set(dirList1))) == 0 or os.path.exists(folder + "/New Folder") is True or os.path.exists(folder + "/untitled folder") is True:
        print "No new directory detected in " + bcolors._YELLOW + "["+ folder + "]" + bcolors._NORM + ": probing again in " + bcolors._YELLOW + str(sleepy) + bcolors._NORM +" seconds"
        time.sleep(sleepy)
        dirList2 = [x[0] for x in os.walk(folder)]
    newDir = list(set(dirList2) - set(dirList1))
    newDir = ''.join(newDir)
    print ""   
    print bcolors._GREEN + "Woof! " + bcolors._NORM + "Found the new directory " + bcolors._GREEN + newDir + bcolors._NORM + ", checking update status"
    print ""
    time.sleep(5)
    diffsize(newDir,clipFile)
    CMD = "echo " + clipFile + " | rev | cut -d '/' -f1,2,3 | rev"
    relClipFile = os.popen(CMD).read().rstrip('\n')
    notifyOS(relClipFile)
    print ""
    print "Will resume probing for new directories"
    print ""
    diffdir(folder,clipFile)

#-------------------------------------------------------------------------------
#
#
def diffsize(newDir,clipFile):
    dirSize1 = get_size(newDir)
    time.sleep(2)
    dirSize2 = get_size(newDir)
    while int(dirSize2) == 0 or dirSize2 != dirSize1:
        print bcolors._GREEN + newDir + bcolors._RED + " still updating!" + bcolors._NORM + " reprobing in " + bcolors._YELLOW + str(sleepy) + bcolors._NORM + " seconds"
        dirSize1 = get_size(newDir)
        time.sleep(sleepy)
        dirSize2 = get_size(newDir)
    print ""
    print bcolors._GREEN + "no updates detected! " + bcolors._NORM + "beginning creation of new .clip version for: "
    print bcolors._ORANGE + clipFile + bcolors._NORM
    print ""
    CMD = "echo " + newDir + " | rev | cut -d '/' -f1,2 | rev" 
    relPath = os.popen(CMD).read().rstrip('\n')
    createClip(newDir,clipFile,relPath)

#-------------------------------------------------------------------------------
#
#
def get_size(newDir):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(newDir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size

#-------------------------------------------------------------------------------
#
#
def notifyOS(relClipFile):
    osType = os.uname()[0]
    if os.uname()[0] == "Linux":
        os.environ["DISPLAY"] = "0:0"
        os.system("xhost + > /dev/null")
        nsArg = relClipFile + " updated"
        CMD = "notify-send " + nsArg + " 2> /dev/null"
        os.system(CMD)
    elif os.uname()[0] == "Darwin":
        from pync import Notifier
        Notifier.notify("updated", title=relClipFile)



###################################################################
#
# MAIN
#
###################################################################

if __name__=='__main__':
   os.system('clear')

   parser = optparse.OptionParser()

   parser.add_option("--menu", action="store_true", dest="menu", default="False", help="[default] use this option to go thru the script's menu")
   parser.add_option("--clip", dest="clipFile", help="clip file to create or append to if already created           (ex: /PROJECTS/SHOTS/SHOT_001/SHOT_001.clip " )
   parser.add_option("--folder", dest="folder", help="folder to be watched:                                         (ex: /PROJECTS/SHOTS/SHOT_001/) " )
   (options, args) = parser.parse_args()
   

   if options.menu is True:
      ccmenu()
   else:
      if options.clipFile is None and options.folder is None:
         ccmenu()


   if os.path.exists(options.folder) is False:
       print "Path not existing, will be created"
       print ""
       os.system("mkdir -p " + options.folder)
       os.system("chmod 777 " + options.folder)

   if not os.path.isdir(options.folder):
       print "Please specify a folder."
       print ""
       sys.exit(2) 
   diffdir(options.folder,options.clipFile)

