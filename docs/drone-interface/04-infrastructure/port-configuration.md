# Port Configuration Reference

This document provides a complete reference for network ports used in PixEagle's drone interface stack.

## Port Summary

### MAVLink Ports

| Port | Protocol | Component | Direction | Purpose |
|------|----------|-----------|-----------|---------|
| 14540 | UDP | PX4 SITL | In/Out | Default SITL MAVLink |
| 14541 | UDP | MAVSDK | Out | PixEagle commands |
| 14550 | UDP | QGroundControl | Out | Ground station |
| 14551 | UDP | MAVLink2REST | Out | REST API source |
| 18570 | UDP | PX4 Secondary | In/Out | Alternative port |

### Application Ports

| Port | Protocol | Component | Purpose |
|------|----------|-----------|---------|
| 8088 | HTTP | MAVLink2REST | REST API server |
| 8000 | HTTP | FastAPI | PixEagle dashboard API |
| 5760 | TCP | mavlink-router | TCP MAVLink server |
| 12345 | UDP | TelemetryHandler | Dashboard broadcast |

## Detailed Port Descriptions

### 14540 - PX4 SITL Default

**Purpose**: Primary MAVLink connection for PX4 SITL

**Usage**:
```bash
# PX4 SITL listens/sends on this port
make px4_sitl_default jmavsim

# mavlink-router receives from SITL
mavlink-routerd 0.0.0.0:14540 ...

# MAVSDK connects (if not using router)
await drone.connect("udp://:14540")
```

**Configuration**:
```yaml
px4:
  connection_string: "udp://:14540"
```

### 14541 - MAVSDK Connection

**Purpose**: Dedicated port for MAVSDK (PixEagle commands)

**Why separate port**:
- Isolates command traffic from telemetry
- Prevents port conflicts with QGC
- Enables independent debugging

**Usage**:
```python
# PX4InterfaceManager connection
await self.drone.connect("udp://:14541")
```

**mavlink-router config**:
```ini
[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541
```

### 14550 - Ground Station

**Purpose**: Standard port for ground control stations

**Usage**:
- QGroundControl auto-connects to this port
- Mission Planner uses this port
- MAVProxy default port

**mavlink-router config**:
```ini
[UdpEndpoint qgc]
Mode = Normal
Address = 127.0.0.1
Port = 14550
```

### 14551 - MAVLink2REST Source

**Purpose**: MAVLink feed for REST API conversion

**Usage**:
```bash
# MAVLink2REST receives MAVLink here
mavlink2rest --mavlink udpin:0.0.0.0:14551

# mavlink-router routes to this port
[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

### 8088 - MAVLink2REST API

**Purpose**: HTTP REST API server

**Endpoints**:
```
GET http://localhost:8088/mavlink/vehicles
GET http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE
GET http://localhost:8088/mavlink/vehicles/1/components/1/messages/ALTITUDE
```

**Configuration**:
```yaml
mavlink2rest:
  base_url: "http://localhost:8088"
```

### 8000 - FastAPI Dashboard

**Purpose**: PixEagle web dashboard API

**Endpoints**:
```
GET  http://localhost:8000/api/status
GET  http://localhost:8000/api/tracker
POST http://localhost:8000/api/follower/start
```

### 12345 - Telemetry Broadcast

**Purpose**: UDP broadcast for dashboard updates

**Usage**:
```python
# TelemetryHandler sends to this port
self.udp_socket.sendto(data, ("localhost", 12345))
```

**Configuration**:
```yaml
telemetry:
  udp_port: 12345
  broadcast_rate_hz: 20
```

## Port Allocation by Component

### mavlink-router

```
Inputs:
  - 14540 UDP (from SITL)
  - Serial (from hardware)

Outputs:
  - 14541 UDP (to MAVSDK)
  - 14550 UDP (to QGC)
  - 14551 UDP (to MAVLink2REST)
  - 5760 TCP (MAVLink TCP server)
```

### MAVLink2REST

```
Inputs:
  - 14551 UDP (from mavlink-router)

Outputs:
  - 8088 HTTP (REST API)
```

### PixEagle

```
Inputs:
  - 8088 HTTP (from MAVLink2REST)

Outputs:
  - 14541 UDP (to MAVSDK/mavlink-router)
  - 8000 HTTP (dashboard API)
  - 12345 UDP (telemetry broadcast)
```

## Firewall Configuration

### Ubuntu UFW

```bash
# Allow MAVLink ports
sudo ufw allow 14540/udp
sudo ufw allow 14541/udp
sudo ufw allow 14550/udp
sudo ufw allow 14551/udp

# Allow application ports
sudo ufw allow 8088/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 12345/udp

# Enable firewall
sudo ufw enable
```

### iptables

```bash
# Allow MAVLink
iptables -A INPUT -p udp --dport 14540 -j ACCEPT
iptables -A INPUT -p udp --dport 14541 -j ACCEPT
iptables -A INPUT -p udp --dport 14550 -j ACCEPT
iptables -A INPUT -p udp --dport 14551 -j ACCEPT

# Allow HTTP
iptables -A INPUT -p tcp --dport 8088 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

## Network Diagrams

### SITL Setup

```
┌──────────────────────────────────────────────────────────────────┐
│                          localhost                                │
│                                                                   │
│  ┌─────────┐        ┌────────────────┐        ┌──────────────┐  │
│  │PX4 SITL │──14540─►│ mavlink-router │──14541─►│   MAVSDK     │  │
│  │         │        │                │──14550─►│(PixEagle)    │  │
│  └─────────┘        │                │──14551─►└──────────────┘  │
│                     └────────────────┘               │           │
│                                │                     │           │
│                                ▼                     │           │
│                     ┌────────────────┐              │           │
│                     │  MAVLink2REST  │──────────────┘           │
│                     │    :8088       │                           │
│                     └────────────────┘                           │
│                                                                   │
│  Dashboard: http://localhost:8000                                │
└──────────────────────────────────────────────────────────────────┘
```

### Production Setup (Companion Computer)

```
┌─────────────────────────────────────────────────────────────────┐
│                      Companion Computer                          │
│                       (192.168.1.20)                             │
│                                                                   │
│  Serial ───────────► mavlink-router ───► MAVLink2REST :8088     │
│  /dev/ttyAMA0              │                    │                │
│                            │                    │                │
│                            ▼                    ▼                │
│                    PixEagle ◄────────────────────               │
│                    :8000 (API)                                   │
│                    :12345 (Telemetry)                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
           │
           │ MAVLink (serial)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flight Controller                           │
│                       (Pixhawk 6)                                │
└─────────────────────────────────────────────────────────────────┘
```

## Changing Default Ports

### PixEagle Configuration

```yaml
# config_default.yaml

px4:
  connection_string: "udp://:14541"  # Change MAVSDK port

mavlink2rest:
  base_url: "http://localhost:8088"  # Change REST port

fastapi:
  port: 8000  # Change dashboard port

telemetry:
  udp_port: 12345  # Change broadcast port
```

### mavlink-router

```ini
# main.conf
[UdpEndpoint custom_mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 15540  # Custom port
```

### MAVLink2REST

```bash
# Custom ports
mavlink2rest \
    --mavlink udpin:0.0.0.0:15551 \
    --server 0.0.0.0:9088
```

## Troubleshooting

### Check Port Usage

```bash
# List all listening ports
sudo netstat -tulnp

# Check specific port
sudo lsof -i :14540

# UDP ports only
sudo netstat -ulnp | grep -E "14540|14541|14550|14551"
```

### Port Conflict Resolution

```bash
# Find process using port
sudo lsof -i :14540

# Kill process
sudo kill -9 <PID>

# Or use different port in config
```

### Test Port Connectivity

```bash
# Test UDP port
nc -vzu localhost 14540

# Test TCP port
nc -vz localhost 8088

# Send test data
echo "test" | nc -u localhost 14540
```

## Related Documentation

- [mavlink-router Setup](mavlink-router.md) - Routing configuration
- [MAVLink2REST Setup](mavlink-anywhere.md) - REST API setup
- [Hardware Connection](hardware-connection.md) - Physical connections
