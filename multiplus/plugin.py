#!/usr/bin/env python
"""
Victron Energy Multiplus II plugin
Author: Xavier Beaudouin
Requirements: 
    1. multiplus + GX
    2. pymodbus AND pymodbusTCP
"""
"""
<plugin key="VictronEnergy_MultiplusII" name="Victron Energy Multiplus II + Modbus" author="Xavier Beaudouin" version="0.0.2" externallink="https://github.com/xbeaudouin/victron-energy-domoticz/mppt">
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

    def strget(self):
        return str(sum(self.samples) / len(self.samples))


#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Maximum class can be used to calculate the highest value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#

#class Maximum:
#
#    def __init__(self):
#        self.samples = []
#        self.max_samples = 30
#
#    def set_max_samples(self, max):
#        self.max_samples = max
#        if self.max_samples < 1:
#            self.max_samples = 1
#
#    def update(self, new_value, scale = 0):
#        self.samples.append(new_value * (10 ** scale))
#        while (len(self.samples) > self.max_samples):
#            del self.samples[0]
#
#        Domoticz.Debug("Maximum: {} - {} values".format(self.get(), len(self.samples)))
#
#    def get(self):
#        return max(self.samples)

# Plugin itself
class BasePlugin:
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
        # Multiplus Devices
        if 1 not in Devices:
            Domoticz.Device(Name="Voltage IN L1",          Unit=1,  TypeName="Voltage", Used=0).Create()
        if 2 not in Devices:
            Domoticz.Device(Name="Current IN L1",          Unit=2,  TypeName="Current (Single)", Used=0).Create()
        if 3 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Power IN L1",            Unit=3,  TypeName="Custom", Used=0, Options=Options).Create()
        if 4 not in Devices:
            Options = { "Custom": "1;Hz" }
            Domoticz.Device(Name="Frequency IN L1",        Unit=4,  TypeName="Custom", Used=0, Options=Options).Create()
        if 5 not in Devices:
            Domoticz.Device(Name="Voltage OUT L1",         Unit=5,  TypeName="Voltage", Used=0).Create()
        if 6 not in Devices:
            Domoticz.Device(Name="Current OUT L1",         Unit=6,  TypeName="Current (Single)", Used=0).Create()
        if 7 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Power OUT L1",           Unit=7,  TypeName="Custom", Used=0, Options=Options).Create()
        if 8 not in Devices:
            Options = { "Custom": "1;Hz" }
            Domoticz.Device(Name="Frequency OUT L1",       Unit=8,  TypeName="Custom", Used=0, Options=Options).Create()
        if 9 not in Devices:
            Domoticz.Device(Name="Grid Lost",              Unit=9,  TypeName="Alert", Used=0).Create()
        if 10 not in Devices:
            Domoticz.Device(Name="VE.Bus State",           Unit=10, TypeName="Text", Used=0).Create()
        
        # Battery
        if 20 not in Devices:
            Domoticz.Device(Name="Battery Voltage",        Unit=20, TypeName="Voltage", Used=0).Create()
        if 21 not in Devices:
            Domoticz.Device(Name="Battery Current",        Unit=21, TypeName="Current (Single)", Used=0).Create()
        if 22 not in Devices:
            Domoticz.Device(Name="Battery SOC",            Unit=22, TypeName="Percentage", Used=0).Create()
        if 23 not in Devices:
            Domoticz.Device(Name="Battery Temperature",    Unit=23, TypeName="Temperature", Used=0).Create()

        # Victron
        if 30 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Grid Power L1",              Unit=30, TypeName="Custom", Used=0, Options=Options).Create()
        if 31 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Consumption L1",             Unit=31, TypeName="Custom", Used=0, Options=Options).Create()
        if 32 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="PV on Output",               Unit=32, TypeName="Custom", Used=0, Options=Options).Create()
        if 33 not in Devices:
            Options = { "Custom": "1;W" }
            Domoticz.Device(Name="Battery Power",              Unit=33, TypeName="Custom", Used=0, Options=Options).Create()
        if 34 not in Devices:
            Domoticz.Device(Name="ESS Battery Life State",     Unit=34, TypeName="Text", Used=0).Create()
        if 35 not in Devices:
            Domoticz.Device(Name="ESS Battery Life SoC Limit", Unit=35, TypeName="Percentage", Used=0).Create()

        return


    def onStop(self):
        Domoticz.Debugging(0)

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
            Devices[9].Update(1, "0")
            Devices[10].Update(1, "0")

        # Ac In Voltage
        self.acInVoltage.update(round(getmodbus16(3, client)/10.0, 3))
        Devices[1].Update(1, self.acInVoltage.strget())

        # Ac In Current
        self.acInCurrent.update(round(getmodbus16(6, client)/10.0, 3))
        Devices[2].Update(1, self.acInCurrent.strget())

        # Ac In Power
        self.acInPower.update(round(getmodbus16(12, client)/0.1, 3))
        Devices[3].Update(1, self.acInPower.strget())

        # Ac In Frequency
        self.acInFrequency.update(round(getmodbus16(9, client)/100.0, 3))
        Devices[4].Update(1, self.acInFrequency.strget())

        # Ac Out Voltage
        self.acOutVoltage.update(round(getmodbus16(15, client)/10.0, 3))
        Devices[5].Update(1, self.acOutVoltage.strget())

        # Ac Out Current
        self.acOutCurrent.update(round(getmodbus16(18, client)/10.0, 3))
        Devices[6].Update(1, self.acOutCurrent.strget())

        # Ac Out Power
        self.acOutPower.update(round(getmodbus16(23, client)/0.1, 3))
        Devices[7].Update(1, self.acOutPower.strget())

        # Ac Out Frequency
        self.acOutFrequency.update(round(getmodbus16(21, client)/100.0, 3))
        Devices[8].Update(1, self.acOutFrequency.strget())

        # Grid lost
        value = getmodbus16(61, client)
        if value == 0:
            Devices[9].Update(nValue=value, sValue="Ok")
        elif value == 2:
            Devices[9].Update(nValue=value, sValue="Alert - Grid Lost")
        else:
            Devices[9].Update(nValue=3,     sValue="Unknown state ?")

        # VE.Bus state
        value = getmodbus16(31, client)
        vebus = 'Unknown?'
        if value == 0: 
            vebus = 'Off'
        elif value == 1:
            vebus = 'Low Power'
        elif value == 2:
            vebus = 'Fault'
        elif value == 3:
            vebus = 'Bulk'
        elif value == 4:
            vebus = 'Absorption'
        elif value == 5:
            vebus = 'Float'
        elif value == 6:
            vebus = 'Storage'
        elif value == 7:
            vebus = 'Equalize'
        elif value == 8:
            vebus = 'Passthru'
        elif value == 9:
            vebus = 'Inverting'
        elif value == 10:
            vebus = 'Power assist'
        elif value == 11:
            vebus = 'Power supply'
        Devices[10].Update(1, str(value)+": "+vebus)
                

        # Multiplus devices
        Domoticz.Debug("Multiplus Interface : IP="+self.IPAddress +", Port="+str(self.IPPort)+" ID="+str(self.BattAddr))
        try:
            battery = ModbusClient(host=self.IPAddress, port=self.IPPort, unit_id=self.BattAddr, auto_open=True, auto_close=True, timeout=2)
        except:
            Domoticz.Error("Error connecting to TCP/Interface on address : "+self.IPaddress+":"+str(self.IPPort))
            # Set value to 0 -> Error on all devices
            Devices[20].Update(1, "0")
            Devices[21].Update(1, "0")
            Devices[22].Update(1, "0")
            Devices[23].Update(1, "0")

        # Battery Voltage
        self.batteryVoltage.update(round(getmodbus16(259, battery)/100.0, 3))
        Devices[20].Update(1, self.batteryVoltage.strget())

        # Battery Current
        self.batteryCurrent.update(round(getmodbus16(261, battery)/10.0,3))
        Devices[21].Update(1, self.batteryCurrent.strget())

        # Battery SOC
        self.batterySoc.update(round(getmodbus16(266, battery)/10.0,3))
        Devices[22].Update(1, self.batterySoc.strget())

        # Battery Temperature
        self.batteryTemp.update(round(getmodbus16(262, battery)/10.0,3))
        Devices[23].Update(1, self.batteryTemp.strget())

        # Victron devices
        Domoticz.Debug("Multiplus Interface : IP="+self.IPAddress +", Port="+str(self.IPPort)+" ID="+str(self.MBAddr))
        try:
            victron = ModbusClient(host=self.IPAddress, port=self.IPPort, unit_id=self.MBAddr, auto_open=True, auto_close=True, timeout=2)
        except:
            Domoticz.Error("Error connecting to TCP/Interface on address : "+self.IPaddress+":"+str(self.IPPort))
            # Set value to 0 -> Error on all devices
            Devices[30].Update(1, "0")
            Devices[31].Update(1, "0")
            Devices[32].Update(1, "0")
            Devices[33].Update(1, "0")
            Devices[34].Update(1, "0")
            Devices[35].Update(1, "0")

        # Grid Power L1
        self.gridpower.update(getmodbus16(820, victron))
        Devices[30].Update(1, self.gridpower.strget())

        # Consumption L1
        self.conso.update(getmodbus16(817, victron))
        Devices[31].Update(1, self.conso.strget())

        # PV on Output
        self.pv.update(getmodbus16(808, victron))
        Devices[32].Update(1, self.pv.strget())

        # Battery Power
        self.batteryPower.update(getmodbus16(842, victron))
        Devices[33].Update(1, self.batteryPower.strget())

        # ESS Battery State
        value = getmodbus16(2900, victron)
        batterystate = "Unknown?"
        onbattery = 0
        if value == 0:
            batterystate = "Unused, Battery Life Disabled"
        elif value == 1:
            batterystate = "Restarted"
        elif value == 2:
            batterystate = "Self-compsumption"
            onbattery = 1
        elif value == 3:
            batterystate = "Self-compsumption, SoC exceeds 85%"
            onbattery = 1
        elif value == 4:
            batterystate = "Self-compsumption, SoC at 100%"
            onbattery = 1
        elif value == 5:
            batterystate = "Discharge disabled"
        elif value == 6:
            batterystate = "Force Charge"
        elif value == 7:
            batterystate = "Sustain"
        elif value == 9:
            batterystate = "Keep batteries charged"
        elif value == 10:
            batterystate = "Battery Life disabled"
        elif value == 11:
            batterystate = "Battery Life disabled (low SoC)"
        Devices[34].Update(1, str(value)+": "+batterystate)
        # TODO: add a device to say on battery yes/no
        # use the "onbattery" variable

        # ESS Battery Life SoC Limit
        value = (getmodbus16(2903, victron) / 10.0)
        Devices[35].Update(1, str(value))

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


# get Modbus 16 bits values
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

