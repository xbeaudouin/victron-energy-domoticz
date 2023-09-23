#!/usr/bin/env python
"""
Victron Energy MPPT plugin
Author: Xavier Beaudouin
Requirements: 
    1. multiplus + GX
    2. pymodbus AND pymodbusTCP
"""
"""
<plugin key="VictronEnergy_GX_MPPT" name="Victron Energy MPPT over GX + Modbus" author="Xavier Beaudouin" version="0.0.2" externallink="https://github.com/xbeaudouin/victron-energy-domoticz/mppt">
    <params>
        <param field="Address" label="GX IP Address" width="150px" required="true" />
        <param field="Port" label="GX Modbus Port Number" width="100px" required="true" default="502" />
        <param field="Mode3" label="Modbus address" width="100px" required="true" default="229" />
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
    def __init__(self):
        # Voltage for last 5 minutes
        self.voltage=Average()
        # Current for last 5 minutes
        self.current=Average()
        # Power factor for last 5 minutes
        self.power=Average()

        return

    def onStart(self):
        try:
            Domoticz.Log("Victron Energy MPPT over GX + Modbus loaded!, using python v" + sys.version[:6] + " and pymodbus v" + pymodbus.__version__)
        except:
            Domoticz.Log("Victron Energy MPPT over GX + Modbus loaded!")

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

        Domoticz.Debug("Query IP " + self.IPAddress + ":" + str(self.IPPort) +" on device : "+str(self.MBAddr))

        # Create the devices if they does not exists
        if 1 not in Devices:
            Domoticz.Device(Name="Voltage",      Unit=1, TypeName="Voltage", Used=0).Create()
        if 2 not in Devices:
            Domoticz.Device(Name="Current",      Unit=2, TypeName="Current (Single)", Used=0).Create()
        if 3 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Power",        Unit=3, TypeName="Custom", Used=0, Options=Options).Create()
        if 4 not in Devices:
            Domoticz.Device(Name="Total Energy", Unit=4, Type=243, Subtype=29, Used=0).Create()

        return


    def onStop(self):
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        Domoticz.Debug(" Interface : IP="+self.IPAddress +", Port="+str(self.IPPort)+" ID="+str(self.MBAddr))
        try:
            client = ModbusClient(host=self.IPAddress, port=self.IPPort, unit_id=self.MBAddr, auto_open=True, auto_close=True, timeout=2)
        except:
            Domoticz.Error("Error connecting to TCP/Interface on address : "+self.IPaddress+":"+str(self.IPPort))
            # Set value to 0 -> Error on all devices
            Devices[1].Update(1, "0")
            Devices[2].Update(1, "0")
            Devices[3].Update(1, "0")
            Devices[4].Update(1, "0")

        total_e = "0"
        power = "0"

        # Voltage
        value = round (getmodbus16(776, client) / 100.0, 3)
        self.voltage.update(value)
        value = self.voltage.get()
        Devices[1].Update(1, str(value))

        # Current
        value = round (getmodbus16(777,client) / 10.0, 3)
        self.current.update(value)
        value = self.current.get()
        Devices[2].Update(1, str(value))

        # Power
        value = round (getmodbus16(789, client) / 10.0, 3)
        self.power.update(value)
        value = self.power.get()
        Devices[3].Update(1, str(value))
        power = str(value)

        # Total Energy
        total_e = str(getmodbus16(790,client)*100)
        Devices[4].Update(1, sValue=power+";"+total_e)


global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

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

# get Modbug 16 bits values
def getmodbus16(register, client):
    value = 0
    try:
        data = client.read_holding_registers(register, 1)
        Domoticz.Debug("Data from register "+str(register)+": "+str(data))
        #decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
        decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.BIG, wordorder=Endian.BIG)
        value = decoder.decode_16bit_int()
    except:
        Domoticz.Error("Error getting data from "+str(register) + ", try 1")
        try:
            data = client.read_holding_registers(register, 1)
            Domoticz.Debug("Data from register "+str(register)+": "+str(data))
            #decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.Big, wordorder=Endian.Big)
            decoder = BinaryPayloadDecoder.fromRegisters(data, byteorder=Endian.BIG, wordorder=Endian.BIG)
            value = decoder.decode_16bit_int()
        except:
            Domoticz.Error("Error getting data from "+str(register) + ", try 2")

    return value

