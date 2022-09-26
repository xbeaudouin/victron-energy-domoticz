#!/usr/bin/env python
"""
Victron Energy Multiplus II plugin
Author: Xavier Beaudouin
Requirements: 
    1. multiplus + GX
    2. pymodbus AND pymodbusTCP
"""
"""
<plugin key="VictronEnergy_MultiplusII" name="Victron Energy Multiplus II + Modbus" author="Xavier Beaudouin" version="0.0.1" externallink="https://github.com/xbeaudouin/victron-energy-domoticz/mppt">
    <params>
        <param field="Address" label="GX IP Address" width="150px" required="true" />
        <param field="Port" label="GX Modbus Port Number" width="100px" required="true" default="502" />
        <param field="Mode3" label="GX Modbus address" width="100px" required="true" default="100" />
        <param field="Mode4" label="Multiplus Modbus address" width="100px" required="true" default="228" />
        <param field="Mode5" label="Battery Modbus address" width="100px" required="true" default="225" />
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import sys

sys.path.append('/usr/local/lib/python3.4/dist-packages')
sys.path.append('/usr/local/lib/python3.5/dist-packages')
sys.path.append('/usr/local/lib/python3.6/dist-packages')
sys.path.append('/usr/local/lib/python3.7/dist-packages')
sys.path.append('/usr/local/lib/python3.8/dist-packages')
sys.path.append('/usr/local/lib/python3.9/dist-packages')
sys.path.append('/usr/local/lib/python3.10/dist-packages')

import pymodbus

from pyModbusTCP.client import ModbusClient
from pymodbus.constants import Endian
from pymodbus.payload   import BinaryPayloadDecoder

#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Average class can be used to calculate the average value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#

class Average:

    def __init__(self):
        self.samples = []
        self.max_samples = 30

    def set_max_samples(self, max):
        self.max_samples = max
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        Domoticz.Debug("Average: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        return sum(self.samples) / len(self.samples)

#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Maximum class can be used to calculate the highest value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#

class Maximum:

    def __init__(self):
        self.samples = []
        self.max_samples = 30

    def set_max_samples(self, max):
        self.max_samples = max
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        Domoticz.Debug("Maximum: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        return max(self.samples)

# Plugin itself
class BasePlugin:
    #enabled = False
    def __init__(self):
        # AC IN Voltage for last 5 minutes
        self.acInVoltage=Average()
        # AC IN Current for last 5 minutes
        self.acInCurrent=Average()
        # AC IN Power for last 5 minutes
        self.acInPower=Average()
        # AC IN Frequency for last 5 minutes
        self.acInFrequency=Average()
        # AC Out Voltage for last 5 minutes
        self.acOutVoltage=Average()
        # AC Out Current for last 5 minutes
        self.acOutCurrent=Average()
        # AC Out Power for last 5 minutes
        self.acOutPower=Average()
        # AC Out Frequency for last 5 minutes
        self.acOutFrequency=Average()
        # Battery Voltage for last 5 minutes
        self.batteryVoltage=Average()
        # Battery Current for last 5 minutes
        self.batteryCurrent=Average()
        # Battery SOC for last 5 minutes
        self.batterySoc=Average()
        # Battery Temperature for last 5 minutes
        self.batteryTemp=Average()
        # Grid Power for last 5 minutes
        self.gridpower=Average()
        # Consumption for last 5 minutes
        self.conso=Average()
        # PV on output for last 5 minutes
        self.pv=Average()
        # Battery power on last 5 minutes
        self.batteryPower=Average()

        return

    def onStart(self):
        try:
            Domoticz.Log("Victron Energy Multiplus-II Modbus loaded!, using python v" + sys.version[:6] + " and pymodbus v" + pymodbus.__version__)
        except:
            Domoticz.Log("Victron Energy Multiplus-II Modbus loaded!")

        # Check dependancies
        try:
            if (float(Parameters["DomoticzVersion"][:6]) < float("2020.2")): Domoticz.Error("WARNING: Domoticz version is outdated or not supported. Please update!")
            if (float(sys.version[:1]) < 3): Domoticz.Error("WARNING: Python3 should be used !")
            if (float(pymodbus.__version__[:3]) < float("2.3")): Domoticz.Error("WARNING: pymodbus version is outdated, please update!")
        except:
            Domoticz.Error("Warning ! Dependancies could not be checked !")

        # Parse parameters
        
        # Debug
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
        else:
            Domoticz.Debugging(0)

        self.IPAddress = Parameters["Address"]
        self.IPPort    = Parameters["Port"]
        self.MBAddr    = int(Parameters["Mode3"])
        self.MultiAddr = int(Parameters["Mode4"])
        self.BattAddr  = int(Parameters["Mode5"])


        Domoticz.Debug("Query IP " + self.IPAddress + ":" + str(self.IPPort) +" on GX device : "+str(self.MBAddr)+" Multi Device : "+str(self.MultiAddr)+" and Battery : "+str(self.BattAddr))

        # Create the devices if they does not exists
        # TODO: refactor this.
        # Multiplus Devices
        if 1 not in Devices:
            Domoticz.Device(Name="Voltage IN L1",       Unit=1,  TypeName="Voltage", Used=0).Create()
        if 2 not in Devices:
            Domoticz.Device(Name="Current IN L1",       Unit=2,  TypeName="Current (Single)", Used=0).Create()
        if 3 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Power IN L1",         Unit=3,  TypeName="Custom", Used=0, Options=Options).Create()
        if 4 not in Devices:
            Options = { "Custom": "1;Hz" }
            Domoticz.Device(Name="Frequency IN L1",     Unit=4,  TypeName="Custom", Used=0, Options=Options).Create()
        if 5 not in Devices:
            Domoticz.Device(Name="Voltage OUT L1",      Unit=5,  TypeName="Voltage", Used=0).Create()
        if 6 not in Devices:
            Domoticz.Device(Name="Current OUT L1",      Unit=6,  TypeName="Current (Single)", Used=0).Create()
        if 7 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Power OUT L1",        Unit=7,  TypeName="Custom", Used=0, Options=Options).Create()
        if 8 not in Devices:
            Options = { "Custom": "1;Hz" }
            Domoticz.Device(Name="Frequency OUT L1",    Unit=8,  TypeName="Custom", Used=0, Options=Options).Create()
        #if 9 not in Devices:
        #   Grid lost Alarm
        
        # Battery
        if 20 not in Devices:
            Domoticz.Device(Name="Battery Voltage",     Unit=20, TypeName="Voltage", Used=0).Create()
        if 21 not in Devices:
            Domoticz.Device(Name="Battery Current",     Unit=21,  TypeName="Current (Single)", Used=0).Create()
        if 22 not in Devices:
            Domoticz.Device(Name="Battery SOC",         Unit=22,  TypeName="Percentage", Used=0).Create()
        if 23 not in Devices:
            Domoticz.Device(Name="Battery Temperature", Unit=23,  TypeName="Temperature", Used=0).Create()

        # Victron
        if 30 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Grid Power L1",       Unit=30,  TypeName="Custom", Used=0, Options=Options).Create()
        if 31 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Consumption L1",      Unit=31,  TypeName="Custom", Used=0, Options=Options).Create()
        if 32 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="PV on Output",        Unit=32,  TypeName="Custom", Used=0, Options=Options).Create()
        if 33 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Battery Power",       Unit=33,  TypeName="Custom", Used=0, Options=Options).Create()
        #if 34 not in Devices:
        # ESS Batterylife

        return


    def onStop(self):
        Domoticz.Debugging(0)

    def onConnect(self, Connection, Status, Description):
        Domoticz.Log("onConnect called")
        return

    def onMessage(self, Connection, Data):
        Domoticz.Log("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called")

    def onHeartbeat(self):

        # Multiplus devices
        Domoticz.Debug("Multiplus Interface : IP="+self.IPAddress +", Port="+str(self.IPPort)+" ID="+str(self.MultiAddr))
        try:
            client = ModbusClient(host=self.IPAddress, port=self.IPPort, unit_id=self.MultiAddr, auto_open=True, auto_close=True, timeout=2)
        except:
            Domoticz.Error("Error connecting to TCP/Interface on address : "+self.IPaddress+":"+str(self.IPPort))
            # Set value to 0 -> Error on all devices
            Devices[1].Update(1, "0")
            Devices[2].Update(1, "0")
            Devices[3].Update(1, "0")
            Devices[4].Update(1, "0")
            Devices[5].Update(1, "0")
            Devices[6].Update(1, "0")
            Devices[7].Update(1, "0")
            Devices[8].Update(1, "0")

        # Ac In Voltage
        data = client.read_holding_registers(3, 1)
        Domoticz.Debug("Data from register 3: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acInVoltage.update(value)
        value = self.acInVoltage.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[1].Update(1, str(value))

        # Ac In Current
        data = client.read_holding_registers(6, 1)
        Domoticz.Debug("Data from register 6: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10.0
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acInCurrent.update(value)
        value = self.acInCurrent.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[2].Update(1, str(value))

        # Ac In Power
        data = client.read_holding_registers(12, 1)
        Domoticz.Debug("Data from register 12: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 0.1
        value = round (value / 0.1, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acInPower.update(value)
        value = self.acInPower.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[3].Update(1, str(value))

        # Ac In Frequency
        data = client.read_holding_registers(9, 1)
        Domoticz.Debug("Data from register 9: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 100.0
        value = round (value / 100.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acInFrequency.update(value)
        value = self.acInFrequency.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[4].Update(1, str(value))

        # Ac Out Voltage
        data = client.read_holding_registers(15, 1)
        Domoticz.Debug("Data from register 15: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acOutVoltage.update(value)
        value = self.acOutVoltage.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[5].Update(1, str(value))

        # Ac Out Current
        data = client.read_holding_registers(18, 1)
        Domoticz.Debug("Data from register 18: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10.0
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acOutCurrent.update(value)
        value = self.acOutCurrent.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[6].Update(1, str(value))

        # Ac Out Power
        data = client.read_holding_registers(23, 1)
        Domoticz.Debug("Data from register 23: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 0.1
        value = round (value / 0.1, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acOutPower.update(value)
        value = self.acOutPower.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[7].Update(1, str(value))

        # Ac Out Frequency
        data = client.read_holding_registers(21, 1)
        Domoticz.Debug("Data from register 21: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 100.0
        value = round (value / 100.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.acOutFrequency.update(value)
        value = self.acOutFrequency.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[8].Update(1, str(value))


        # Multiplus devices
        Domoticz.Debug("Multiplus Interface : IP="+self.IPAddress +", Port="+str(self.IPPort)+" ID="+str(self.BattAddr))
        try:
            battery = ModbusClient(host=self.IPAddress, port=self.IPPort, unit_id=self.BattAddr, auto_open=True, auto_close=True, timeout=2)
        except:
            Domoticz.Error("Error connecting to TCP/Interface on address : "+self.IPaddress+":"+str(self.IPPort))
            # Set value to 0 -> Error on all devices
            Devices[1].Update(1, "0")
            Devices[2].Update(1, "0")
            Devices[3].Update(1, "0")
            Devices[4].Update(1, "0")
            Devices[5].Update(1, "0")
            Devices[6].Update(1, "0")
            Devices[7].Update(1, "0")
            Devices[8].Update(1, "0")

        # Battery Voltage
        data = battery.read_holding_registers(259, 1)
        Domoticz.Debug("Data from register 259: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 100.0
        value = round (value / 100.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.batteryVoltage.update(value)
        value = self.batteryVoltage.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[20].Update(1, str(value))

        # Battery Current
        data = battery.read_holding_registers(261, 1)
        Domoticz.Debug("Data from register 261: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10.0
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.batteryCurrent.update(value)
        value = self.batteryCurrent.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[21].Update(1, str(value))

        # Battery SOC
        data = battery.read_holding_registers(266, 1)
        Domoticz.Debug("Data from register 266: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10.0
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.batterySoc.update(value)
        value = self.batterySoc.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[22].Update(1, str(value))

        # Battery Temperature
        data = battery.read_holding_registers(262, 1)
        Domoticz.Debug("Data from register 262: "+str(data))
        # Unsigned 16
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        # Value
        value = decoder.decode_16bit_int()
        # Scale factor / 10.0
        value = round (value / 10.0, 3)
        Domoticz.Debug("Value after conversion : "+str(value))
        Domoticz.Debug("-> Calculating average")
        self.batteryTemp.update(value)
        value = self.batteryTemp.get()
        Domoticz.Debug(" = {}".format(value))
        Devices[23].Update(1, str(value))


global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return