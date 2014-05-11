# Version 0.6 vom 11.05.2014

#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import RPi.GPIO as GPIO
import os, urlparse
import time
import datetime
import ConfigParser
import smtplib
from SocketServer import ThreadingMixIn
import threading
from email.mime.text import MIMEText
from array import array
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import fcntl

class  PiBell:
    def __init__(self,configFile="/etc/pibell.conf"):

        self._logObj = LogFile("log")
        self._logObj.writeToLog("starting service")

        #check if Configuration File exists
        if not os.path.isfile(configFile):
            self._logObj.writeToLog("[RaspiPo] configuration file was not found: " + configFile)
            raise Exception("[RaspiPo] configuration file was not found: " + configFile)

        #load configuration file
        self._configuration = ConfigParser.ConfigParser()
        self._configuration.read(configFile)
        self._loadConfigurationItems(self._configuration)
        self._setupGPIOPin(self._listen_gpio_pin)

        #start services
        self._logObj.writeToLog("[RaspiPo] listen on GPIO Pin No. " + str(self._listen_gpio_pin))
        self._run()


    def __del__(self):
        self._logObj.writeToLog("[RaspiPo] shutting down service")

    def _setupGPIOPin(self,gpio_pin):
       GPIO.setmode(GPIO.BOARD)
       GPIO.setwarnings(False)
       GPIO.setup(gpio_pin,GPIO.IN)

    def _loadConfigurationItems(self,configuration):

        section = "Basic Configuration"
        #                   section_name        mandatory   type/string = ''
        optionlist = [     ['scan_period',      True,       'float'],
                           ['idle_time',        True,       'float'],
                           ['listen_gpio_pin',  True,       'int']
                     ]

        for option in optionlist:
            if not configuration.has_option(section,option[0]) and option[1]:
                self._logObj.writeToLog("error in configuration file"  + section + " Option: " + option[0])
                raise Exception("Konfigurationsdatei fehlerhaft"  + section + " Option: " + option[0])
            else:
                method = getattr(configuration,'get'+option[2])
                val = method(section,option[0])
                setattr(self,'_'+option[0],val)

        #check email configuration options
        section = "Email Notification"
        if configuration.has_section(section):
            if not self._configuration.getboolean(section,"email_enable"):
                self._logObj.writeToLog("[Email] email notification is <disbaled>")
            else:
                self._logObj.writeToLog("[Email] email notification is <enabled>")
                #the eMail - Object will load configuration itself.
                self._EmailObj = EmailNotificiation(self._configuration)

        #check webui configuration options
        section = 'WebUI'
        if self._configuration.has_section(section):
            if self._configuration.getboolean(section,"webui_enable"):
                self._webui_port = self._configuration.getint(section,"webui_port")
                self._logObj.writeToLog("[WEBUI] webui started on port " + str(self._webui_port))
                try:
                    self._webui = ThreadedHTTPServer(('',self._webui_port),WebUIRequestHandler)
                    thread = threading.Thread(target=self._webui.serve_forever)
                    thread.setDaemon(True);
                    thread.start()

                except Exception as e:
                    self._logObj.writeToLog("[WEBUI] error when starting the webui: " + e.args[1])

    def _sendEmail(self):
        try:
            self._EmailObj.sendEmail()
        except:
            #email_enable = false
            pass

    def _run(self):
        try:
            while True:
                #do some GPIO things here
                if GPIO.input(self._listen_gpio_pin) == GPIO.LOW:
                    self._logObj.writeToLog("[RaspiPo] <<<<<<  ... signal detected!!! >>>>>")
                    self._sendEmail()
                    #wait the amount of idle time in seconds
                    self._logObj.writeToLog("[RaspiPo] going to sleep for " + str(self._idle_time) + " seconds")
                    time.sleep(self._idle_time)
                time.sleep(self._scan_period)
        except KeyboardInterrupt:
            pass #do nothing
        except Exception as exception:
            self._logObj.writeToLog("[RaspiPo] stop listen on GPIO Pin " + str(self._listen_gpio_pin))

    def _startWebServer(self):
        pass

class EmailNotificiation:
    def __init__(self,configuration,logObj=None):
        if logObj == None:
            self._logObj = LogFile("log")
        else:
            self._logObj = logObj

        self._logObj.writeToLog("[Email] starting email notifciation services")
        self._loadConfiguration(configuration)
        self._logObj.writeToLog("[Email] trying to to reach smtp server")

    def _loadConfiguration(self,configuration):
        self._logObj.writeToLog("[Email] reading email notification config")
        section = "Email Notification"
        #                    section_name           mandatory   type/string = ''
        optionlist = [     ['email_recipient',      True,       ''],
                           ['email_sendername',     True,       ''],
                           ['email_senderaddress',  True,       ''],
                           ['email_server_smtp',    True,       ''],
                           ['email_server_port',    True,       'int'],
                           ['email_loginname',      True,       ''],
                           ['email_loginpassword',  True,       ''],
                           ['email_subject',        True,       ''],
                           ['email_message',        True,       '']
                           ]

        for option in optionlist:
            if not configuration.has_option(section,option[0]) and option[1]:
                self._logObj.writeToLog("[Email] error in configuration file - section"  + section + " option: " + option[0])
                raise Exception("Konfigurationsdatei fehlerhaft"  + section + " Option: " + option[0])
            else:
                method = getattr(configuration,'get'+option[2])
                val = method(section,option[0])
                setattr(self,'_'+option[0],val)


    def sendEmail(self):
        self._logObj.writeToLog("[Email] trying to send email")

        try:
            self._logObj.writeToLog("[Email] say EHLO to STMP server")
            self._SMTPConnection= smtplib.SMTP(self._email_server_smtp,self._email_server_port)
            self._SMTPConnection.ehlo()
            self._logObj.writeToLog("[Email] trying to start secure connection")
            self._SMTPConnection.starttls()
            self._logObj.writeToLog("[Email] logging in to SMTP server")
            self._SMTPConnection.login(self._email_loginname,self._email_loginpassword)
            message = self._createMessage()
            self._logObj.writeToLog("[Email] sending email to " + message['To'])
            self._SMTPConnection.sendmail(message['From'],message['To'],message.as_string())
            self._SMTPConnection.quit()
        except Exception as e:
            self._logObj.writeToLog("[Email]" + e.args[0])


    def _createMessage(self):
        message = self._email_message.replace("&time&",datetime.datetime.now().strftime("%H:%M:%S"))
        message = message.replace("&date&",datetime.datetime.now().strftime("%d.%m.%Y"))
        msg = MIMEText(message)
        msg['Subject'] = self._email_subject
        msg['From']    = self._email_senderaddress
        msg['To']      = self._email_recipient
        return msg

class LogFile:

    def __init__(self,path):
        self._now = datetime.datetime.now()
        self._filename = path + "/" + self._now.strftime("%Y_%m_%d") + " logfile.log"

    def writeToLog(self,message):
        self._now = datetime.datetime.now()
        file = open(sys.path[0] + "/" + self._filename, 'a+')
        file.write(self._now.strftime("%H:%M:%S -> ") + message + "\n")
        file.close()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a seperate thread"""

class WebUIRequestHandler(BaseHTTPRequestHandler):
    #handle GET command

    def do_GET(self):
        self._rootdir = sys.path[0] + "/" + 'webui'
        parsed_path = urlparse.urlparse(self.path)
        self.serve_content(self.path)

    def send_headers(self, path):
        htype = ''
        ftype = ''

        if path.endswith('.js'):
            htype =     'application/javascript'
            ftype = 'r'

        if path.endswith('.css'):
            htype =  'text/css'
            ftype = 'r'

        if path.endswith('.html'):
            htype =  'text/html'
            ftype = 'r'

        if path.endswith('.py'):
            htype = 'text/html'
            ftype = 'execute'

        if path.endswith('.png'):
            htype =  'image/png'
            ftype = 'rb'

        if path.endswith('.jpg'):
            htype =  'image/jpeg'
            ftype = 'rb'

        if path.endswith('.jepg'):
            htype =  'image/jpeg'
            ftype = 'rb'

        if path.endswith('.ico'):
            htype =  'image/x-icon'
            ftype = 'rb'

        if path.endswith('.gif'):
            htype =  'image/gif'
            ftype = 'rb'

        if htype != '':
            self.send_header('Content-type', htype)
            self.end_headers()

        else:
            self.send_header('Content-type', 'text/plain')
            self.end_headers()

        return ftype

    def do_redirect(self, path="/index.html"):
        self.send_response(301)
        self.send_header('Location', path)
        self.end_headers()

    def serve_content(self, path="/"):

        if path == "" or path == "/":
            path = "/index.html"
            self.do_redirect()
        else:
            f2r = self._rootdir + path
            if os.path.isfile(f2r) or path.endswith('.log'):
                try:
                    self.send_response(200)
                    ftype = self.send_headers(path)
                    if ftype != 'execute':
                        if path.endswith('.log'):
                            fopen = open(sys.path[0] + "/log" + path.replace("%20"," "))
                            content = fopen.read()
                        else:
                            fopen = open(self._rootdir + path)
                            content = fopen.read()
                            content = self._parseSpecialChars(content)

                        self.wfile.write(content)
                        fopen.close()
                except Exception as exception:
                    self.send_error(404)
                    self.wfile.write(exception.args[0])
                    self.wfile.write("Requested resource %s unavailable" % str(f2r))
            else:
                self.send_error(404)

    def _parseSpecialChars(self,content_in):
        content = content_in.replace("%head%",open(self._rootdir + "/header.html").read())
        if '%logfilelist%' in content:
            logfilelist =  os.listdir(sys.path[0] + "/log")
            HTMLLogfileList = ''
            for logfile in logfilelist:
                if logfile.endswith(".log"):
                    HTMLLogfileList = HTMLLogfileList + '<a href="' + logfile + '" target="logfileViewer">' + logfile + '</a><br/>'
            content = content.replace("%logfilelist%",HTMLLogfileList)
        return content

def main(configFile="/etc/pibell.conf"):
    if not prog_lock_acq('singleton.lock'):
        print("RaspiPo already running")
        exit(1)

    try:
        print "Starting services..."
        pybell = PiBell(configFile)
    except Exception as exception:
        print "Shutting Down services..."
        print exception.args[0]
        os._exit(os.EX_OK)

def prog_lock_acq(lpath):
    fd = None
    try:
        fd = os.open(lpath, os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_NB | fcntl.LOCK_EX)
        return True
    except(OSError, IOError):
        if fd: os.close(fd)
        return False

if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
