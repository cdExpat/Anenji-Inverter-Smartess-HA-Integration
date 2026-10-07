# Anenji-Inverter-Smartess-HA-Integration

> [!WARNING]
> Not tested yet. Currently redirect from Smartess stick to my laptop as server to homeassistant as mqtt working

> [!NOTE]
> Thanks to samuelolteanu for the big work, take a look at his repository
> 
> https://https://github.com/samuelolteanu/Local-Cloud-Bridge-for-Anenji-Easun-MPP-Solar-Inverters/tree/main

Connect Anenji inverter with Smartess Wifi stick to Home Assistant. The UDP messages are redirected to this integration and data is published to mqtt.

<div align="center">
  
| **Data published** |
| :--- |
| **PV Power** |
| PV Voltage |
| Battery Voltage |
| Battery Capacity Percentage |
| Battery Power |
| AC Load Power |
| Grid Voltage |
| Total Solar Energy |
| Total Load Energy |
| Total Battery Charge Energy |
| Total Battery Discharge Energy |

<div align="left">
I added a screenshot from my current working mqtt:

<div align="center">
<img width="1266" height="843" alt="mqtt anj-4200W" src="https://github.com/user-attachments/assets/464c4a8f-13ca-4325-bb25-5cdd2b19cb3a" />


