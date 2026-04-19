# broadcast_controller.py
# SDN Project #12 - Broadcast Traffic Control
# Author: [Your Name] | SRN: [Your SRN]
# Description: Controls excessive broadcast traffic using Ryu OpenFlow controller.

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4
from ryu.lib.packet import ether_types
import logging
import time

class BroadcastController(app_manager.RyuApp):
    """
    Ryu controller that:
    1. Learns MAC addresses to avoid unnecessary flooding
    2. Detects broadcast packets and limits flooding
    3. Installs selective unicast flow rules
    4. Tracks broadcast stats for evaluation
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(BroadcastController, self).__init__(*args, **kwargs)
        # MAC learning table: {dpid: {mac: port}}
        self.mac_to_port = {}
        # Broadcast statistics
        self.broadcast_count = 0
        self.unicast_count = 0
        self.flood_limited = 0
        self.start_time = time.time()
        self.logger.setLevel(logging.INFO)
        self.logger.info("=== Broadcast Traffic Control Controller Started ===")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry on switch connection."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install a table-miss entry: send unmatched packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("Switch %s connected. Table-miss rule installed.", datapath.id)

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """Helper: install a flow rule on the switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle incoming packets and apply broadcast control logic."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        # Initialize MAC table for this switch
        self.mac_to_port.setdefault(dpid, {})

        # ── STEP 1: Learn the source MAC address ──
        self.mac_to_port[dpid][src] = in_port

        # ── STEP 2: Detect broadcast/multicast ──
        is_broadcast = (dst == 'ff:ff:ff:ff:ff:ff')
        is_multicast = dst.startswith('01:')

        if is_broadcast or is_multicast:
            self.broadcast_count += 1
            self.logger.info(
                "[BROADCAST DETECTED] Switch=%s In-Port=%s Src=%s Dst=%s | "
                "Total broadcasts: %d",
                dpid, in_port, src, dst, self.broadcast_count
            )

            # ── STEP 3: Limit flooding — only flood if we must ──
            # Check if this is an ARP request (necessary broadcast)
            arp_pkt = pkt.get_protocol(arp.arp)
            if arp_pkt:
                self.logger.info(
                    "[ARP] opcode=%s src_ip=%s dst_ip=%s — allowing controlled flood",
                    arp_pkt.opcode, arp_pkt.src_ip, arp_pkt.dst_ip
                )
                # Allow ARP to flood (necessary for host discovery)
                # but do NOT install a flood flow rule (keeps control at controller)
                out_port = ofproto.OFPP_FLOOD
            else:
                # Non-ARP broadcast: limit it — drop or selective forward
                self.flood_limited += 1
                self.logger.warning(
                    "[BROADCAST LIMITED] Non-ARP broadcast dropped. "
                    "Total limited: %d", self.flood_limited
                )
                return  # Drop non-ARP broadcasts

            actions = [parser.OFPActionOutput(out_port)]
            # Do NOT install a flow rule for broadcasts (keep controller in control)

        else:
            # ── STEP 4: Unicast — install selective forwarding rule ──
            self.unicast_count += 1

            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
                self.logger.info(
                    "[UNICAST] Switch=%s Src=%s -> Dst=%s | Port=%s | "
                    "Installing flow rule.",
                    dpid, src, dst, out_port
                )

                # Install a specific flow rule (selective forwarding)
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                actions = [parser.OFPActionOutput(out_port)]
                # idle_timeout=10: rule removed after 10s of inactivity
                self.add_flow(datapath, priority=1, match=match,
                              actions=actions, idle_timeout=10, hard_timeout=30)
            else:
                # Destination unknown — flood temporarily
                out_port = ofproto.OFPP_FLOOD
                self.logger.info(
                    "[UNKNOWN DST] Flooding for dst=%s (will learn on reply)", dst
                )
                actions = [parser.OFPActionOutput(out_port)]

        # ── STEP 5: Send the packet out ──
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Log flow table stats when requested."""
        flows = []
        for stat in ev.msg.body:
            flows.append(
                "Priority=%s Match=%s Actions=%s Packets=%s Bytes=%s" % (
                    stat.priority, stat.match, stat.instructions,
                    stat.packet_count, stat.byte_count
                )
            )
        self.logger.info("=== FLOW TABLE ===\n%s", '\n'.join(flows))

    def print_stats(self):
        """Print broadcast control statistics."""
        elapsed = time.time() - self.start_time
        self.logger.info(
            "\n=== BROADCAST CONTROL STATS (%.1fs) ===\n"
            "  Broadcasts detected : %d\n"
            "  Unicast flows       : %d\n"
            "  Broadcasts limited  : %d\n"
            "  Selective rules installed (see flow table)\n"
            "==========================================",
            elapsed, self.broadcast_count, self.unicast_count, self.flood_limited
        )
