import sys
import RPi.GPIO as GPIO
import os
import time
import datetime
import ConfigParser
import smtplib
from SocketServer import ThreadingMixIn
import threading
from email.mime.text import MIMEText
from array import array
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

class  PiBell:
    def __init__(self,configFile="/etc/pibell.conf"):

        self._logObj = LogFile("log")
        self._logObj.writeToLog("starting service")

        #check if Configuration File exists
        if not os.path.isfile(configFile):
            self._logObj.writeToLog("configuration file was not found: " + configFile)
            raise Exception("configuration file was not found: " + configFile)

        #load configuration file
        self._configuration = ConfigParser.ConfigParser()
        self._configuration.read(configFile)
        self._loadConfigurationItems(self._configuration)
        self._setupGPIOPin(self._listen_gpio_pin)

        #start services
        self._logObj.writeToLog("listen on GPIO Pin No. " + str(self._listen_gpio_pin))
        self._run()


    def __del__(self):
        self._logObj.writeToLog("shutting down service")

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
                self._logObj.writeToLog("email Notification is disbaled")
            else:
                self._logObj.writeToLog("email Notification is enabled")
                #the eMail - Object will load configuration itself.
                self._EmailObj = EmailNotificiation(self._configuration)

        #check webui configuration options
        section = 'WebUI'
        if self._configuration.has_section(section):
            if self._configuration.getboolean(section,"webui_enable"):
                self._webui_port = self._configuration.getint(section,"webui_port")
                self._logObj.writeToLog("webui started on port " + str(self._webui_port))
                try:
                    self._webui = ThreadedHTTPServer(('',self._webui_port),WebUIRequestHandler)
                    threading.Thread(target=self._webui.serve_forever).start()
                except Exception as e:
                    self._logObj.writeToLog("Fehler beim Starten der WEBUI: " + e.args[1])

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
                    self._logObj.writeToLog("hurrayyy ... signal detected!!!")
                    self._sendEmail()
                    #wait the amount of idle time in seconds
                    self._logObj.writeToLog("going to sleep for " + str(self._idle_time) + " seconds")
                    time.sleep(self._idle_time)
                time.sleep(self._scan_period)
        except KeyboardInterrupt:
            pass #do nothing
        except Exception as exception:
            self._logObj.writeToLog("stop listen on GPIO Pin " + str(self._listen_gpio_pin))

    def _startWebServer(self):
        pass

class EmailNotificiation:
    def __init__(self,configuration,logObj=None):
        if logObj == None:
            self._logObj = LogFile("log")
        else:
            self._logObj = logObj

        self._logObj.writeToLog("starting email notifciation services")
        self._loadConfiguration(configuration)
        self._logObj.writeToLog("trying to to reach smtp server")
        self._SMTPConnection= smtplib.SMTP(self._email_server_smtp,self._email_server_port)

    def _loadConfiguration(self,configuration):
        self._logObj.writeToLog("reading email notification config")
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
                self._logObj.writeToLog("error in configuration file - section"  + section + " option: " + option[0])
                raise Exception("Konfigurationsdatei fehlerhaft"  + section + " Option: " + option[0])
            else:
                method = getattr(configuration,'get'+option[2])
                val = method(section,option[0])
                setattr(self,'_'+option[0],val)


    def sendEmail(self):
        self._logObj.writeToLog("trying to send email")
        self._logObj.writeToLog("say EHLO to STMP server")
        self._SMTPConnection.ehlo()
        self._logObj.writeToLog("start secure connection")
        self._SMTPConnection.starttls()
        self._logObj.writeToLog("logging in to SMTP server")
        self._SMTPConnection.login(self._email_loginname,self._email_loginpassword)
        message = self._createMessage()
        self._logObj.writeToLog("sending email to " + message['To'])
        self._SMTPConnection.sendmail(message['From'],message['To'],message.as_string())

    def _createMessage(self):
        self._email_message = str(self._email_message)
        self._email_message = self._email_message.replace("&time&",datetime.datetime.now().strftime("%H:%M:%S"))
        self._email_message = self._email_message.replace("&date&",datetime.datetime.now().strftime("%d.%m.%Y"))
        msg = MIMEText(self._email_message)
        msg['Subject'] = self._email_subject
        msg['From']    = self._email_senderaddress
        msg['To']      = self._email_recipient
        return msg

class LogFile:

    def __init__(self,path):
        self._now = datetime.datetime.now()
        self._filename = path + "/" + self._now.strftime("%Y_%m_%d") + " logfile.log"

    def writeToLog(self,message):
        file = open(sys.path[0] + "/" + self._filename, 'a+')
        file.write(self._now.strftime("%H:%M:%S -> ") + message + "\n")
        file.close()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a seperate thread"""

class WebUIRequestHandler(BaseHTTPRequestHandler):
    #handle GET command

    def do_GET(self):
        rootdir = sys.path[0] + "/" + 'webui/'
        try:
            if self.path == '/':
                self.path = "index.html"
            if self.path.endswith('.html'):
                f = open(rootdir + self.path) #open requested file

                #send code 200 response
                self.send_response(200)

                #send header first
                self.send_header('Content-type','text-html')
                self.end_headers()

                #modify output
                output = f.read()
                output = output.replace("%head%",open(rootdir + "header.html").read())


                if self.path =="/log.html":
                    logfilelist =  os.listdir(sys.path[0] + "/log")
                    HTMLLogfileList = ''
                    for logfile in logfilelist:
                        if logfile.endswith(".log"):
                            HTMLLogfileList = HTMLLogfileList + '<a href="' + logfile + '" target="logfileViewer">' + logfile + '</a><br/>'
                    output = output.replace("%logfilelist%",HTMLLogfileList)

                if self.path == "/config.html":
                    if len(sys.argv) > 1:
                        configFilePath = sys.argv[1]
                    else:
                        configFilePath = "/etc/pibell.conf"

                    configFile = open(configFilePath)
                    configFileContent = configFile.read()
                    configFileContent = configFileContent.replace("\n","<br/>")
                    output = output.replace("%config%",configFileContent)
                    configFile.close()

                #send file content to client
                self.wfile.write(output)
                f.close()
            elif self.path.endswith('.log'):
                dir = sys.path[0] + "/log"
                self.path = self.path.replace("%20"," ")
                f = open(dir + self.path) #open requested file

                #send code 200 response
                self.send_response(200)

                #send header first
                self.send_header('Content-type','text-html')
                self.end_headers()

                #modify output
                output = f.read()

                #send file content to client
                self.wfile.write(output)
                f.close()


                pass
            return


        except IOError:
            self.send_error(404, 'file not found' + dir + self.path)


def main(configFile="/etc/pibell.conf"):
    try:
        print "Starting services..."
        pybell = PiBell(configFile)
    except Exception as exception:
        print exception.args[0]
        print "Shutting Down services..."

if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
