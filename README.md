# SDN Project #12: Broadcast Traffic Control

**Student Name:** Abhay Balakrishna Doddaballapur 
**SRN:** PES1UG24CS012
**Course:** Computer Networks / SDN Lab  

---

## Problem Statement

Excessive broadcast traffic (ARP floods, unknown unicast flooding) degrades network
performance in traditional networks. In SDN, the controller has full visibility of
the network and can intelligently control broadcast behavior. This project implements
an SDN controller that detects broadcast packets, limits unnecessary flooding, and
installs selective unicast forwarding rules — demonstrating measurable improvement
over a naive flood-all approach.

---

## Network Topology
h1 (10.0.0.1) ─┐
h2 (10.0.0.2) ─┤
s1 ──── Ryu Controller (port 6653)
h3 (10.0.0.3) ─┤
h4 (10.0.0.4) ─┘

- 1 OpenFlow 1.3 switch (OVS)
- 4 hosts
- 1 Ryu remote controller

---

## Setup & Execution Steps

### Prerequisites

```bash
sudo apt install -y mininet python3-pip wireshark iperf3
pip3 install ryu --break-system-packages
```

### Step 1 — Start the Broadcast Control Controller

```bash
cd ~/sdn-broadcast-control
ryu-manager broadcast_controller.py --verbose
```

### Step 2 — In a NEW terminal, start the Mininet topology

```bash
cd ~/sdn-broadcast-control
sudo python3 topology.py
```

### Step 3 — Run test scenarios inside Mininet CLI

**Scenario A: All hosts can communicate (functional correctness)**
mininet> pingall

**Scenario B: Observe broadcast control**
mininet> h1 arping -c 5 10.0.0.2
mininet> h2 ping -c 10 h3

**Scenario C: iperf throughput test**
mininet> iperf h1 h4

**Check flow table:**
mininet> sh ovs-ofctl dump-flows s1

---

## Expected Output

- `pingall` → 0% packet loss
- ARP packets are detected and logged by the controller
- Non-ARP broadcasts are dropped (logged as "BROADCAST LIMITED")
- Selective unicast flow rules are installed after MAC learning
- `ovs-ofctl dump-flows s1` shows specific match rules (not just flood)

---

## Test Scenarios

| Scenario | Tool | Expected Result |
|---|---|---|
| All hosts ping | `pingall` | 0% drop |
| ARP detection | `arping` | Controller logs show ARP interception |
| Broadcast limiting | Non-ARP broadcast | Controller drops, logs "BROADCAST LIMITED" |
| Unicast flow install | `ping h1 h4` | Flow rule installed (see `dump-flows`) |
| Throughput | `iperf h1 h4` | Measurable bandwidth |

---

## Proof of Execution

See `/screenshots/` folder for:
- `01_controller_start.png` — Ryu controller running
- `02_topology_start.png` — Mininet topology up
- `03_pingall.png` — All hosts reachable
- `04_broadcast_detected.png` — Controller log showing broadcast detection
- `05_flow_table.png` — `ovs-ofctl dump-flows` output
- `06_iperf_result.png` — Throughput measurement
- `07_wireshark_arp.png` — Wireshark capture of ARP traffic

---

## References

1. Ryu SDN Framework Documentation: https://ryu.readthedocs.io/
2. Mininet Documentation: http://mininet.org/
3. OpenFlow 1.3 Specification: https://opennetworking.org/
4. Open vSwitch Documentation: https://docs.openvswitch.org/
5. "SDN: Software Defined Networks" — Nadeau & Gray, O'Reilly 2013
