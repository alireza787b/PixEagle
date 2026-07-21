# Connection Issues

This guide covers common connection problems and solutions for the drone interface.

## Quick Diagnosis

### Check All Connections

```bash
# 1. MAVLink2REST
curl -s http://127.0.0.1:8088/v1/mavlink/vehicles | jq

# 2. Local MAVLink listeners (a UDP listener alone does not prove packet flow)
ss -lunp | grep -E ':(14540|14569)\b'

# 3. mavlink-router
systemctl status mavlink-router
# or check process
ps aux | grep mavlink
```

## MAVLink2REST Connection Issues

### Symptoms

- "Connection refused" errors
- Empty telemetry data
- Dashboard shows "No Data"

### Solutions

#### 1. MAVLink2REST Not Running

```bash
# Check the local bridge
curl http://127.0.0.1:8088/

# Inspect and restart the owning PixEagle runtime
make status
make stop
make run
```

For an installed service, use `pixeagle-service status` and
`pixeagle-service restart`. Do not start a second standalone MAVLink2REST
process while the PixEagle runtime owns port `8088`.

#### 2. Wrong Port Configuration

```yaml
# config_default.yaml
MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
```

Check what port is actually in use:

```bash
netstat -tlnp | grep mavlink2rest
# or
ss -tlnp | grep 8088
```

#### 3. No Vehicle Connected

```bash
# Check for vehicles
curl http://127.0.0.1:8088/v1/mavlink/vehicles

# Expected: {"vehicles":[1]}
# Problem: {"vehicles":[]}
```

**Fix:** Ensure MAVLink source is connected:
- SITL is running
- Serial connection is established
- mavlink-router is forwarding

#### 4. Firewall Blocking

```bash
# Check firewall
sudo ufw status

# MAVLink2REST is local-only by default. Do not expose 8088 unless a reviewed
# deployment plan requires it.
```

## MAVSDK Connection Issues

### Symptoms

- "Connection timed out"
- "No system found"
- Commands not reaching drone

### Solutions

#### 1. Wrong Connection String

```yaml
# config_default.yaml
PX4:
  SYSTEM_ADDRESS: "udpin://127.0.0.1:14540"
```

Common connection strings:

| Setup | `PX4.SYSTEM_ADDRESS` |
|-------|--------------------|
| SITL via mavlink-router | `udpin://127.0.0.1:14540` |
| SITL direct listener | `udpin://0.0.0.0:14540` |
| Advanced direct serial, single consumer | `serial:///dev/ttyUSB0:921600` |

The maintained default uses a router and the loopback `udpin` endpoint. A direct
serial URI bypasses the default MAVLink2REST route and must not be mixed with the
two-consumer topology. See the
[PX4 connectivity guide](../04-infrastructure/port-configuration.md).

#### 2. Port Already in Use

```bash
# Check what's using the port
lsof -i :14540

# Stop conflicting process
kill <PID>
```

#### 3. mavlink-router Not Forwarding

Check mavlink-router config:

```ini
# /etc/mavlink-router/main.conf
[UdpEndpoint pixeagle]
Mode = Normal
Address = 127.0.0.1
Port = 14540

[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14569
```

Restart after changes:

```bash
sudo systemctl restart mavlink-router
```

#### 4. SITL Not Running

```bash
# Check SITL process
ps aux | grep px4

# Validate or start only the reviewed plan for this checkout
make sitl-sih-dry-run
```

See [SITL Setup](../04-infrastructure/sitl-setup.md) for the pinned image,
explicit execution gate, and evidence workflow.

## Serial Connection Issues

### Symptoms

- "Permission denied" on /dev/ttyUSB0
- "Device not found"
- Intermittent disconnects

### Solutions

#### 1. Permission Denied

```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in, or:
newgrp dialout
```

#### 2. Device Not Found

```bash
# List serial devices
ls -la /dev/tty*

# Check dmesg for device
dmesg | tail -20

# Find USB device
lsusb
```

#### 3. Wrong Baud Rate

Common baud rates:
- **921600** - Most common for Pixhawk
- **57600** - Older firmware
- **115200** - Some configurations

```yaml
PX4:
  SYSTEM_ADDRESS: "serial:///dev/ttyUSB0:921600"
```

#### 4. USB Cable Issues

- Use a data cable (not charge-only)
- Try different USB port
- Use shorter cable
- Try powered USB hub

## Network Connection Issues

### Symptoms

- Works locally but not remotely
- High latency
- Packet loss

### Solutions

#### 1. Check Network Path

```bash
# Ping companion computer
ping 192.168.1.10

# Check route
traceroute 192.168.1.10

# Test local access on the companion over SSH
ssh <user>@192.168.1.10 'curl -fsS http://127.0.0.1:3040 >/dev/null && curl -fsS http://127.0.0.1:5077/status >/dev/null'

# Or create a local tunnel from the GCS/browser machine
ssh -L 3040:127.0.0.1:3040 -L 5077:127.0.0.1:5077 <user>@192.168.1.10
```

Do not probe or open PixEagle backend port `5077` as an anonymous LAN service.
Remote browser/API access needs an explicit credentialed profile, exact
Host/CORS allowlists, and the production hardening gates documented in the API
exposure boundary.

#### 2. WiFi Issues

```bash
# Check signal strength
iwconfig wlan0

# Check connection quality
wavemon
```

**Recommendations:**
- Use 5GHz for lower latency
- Position antenna properly
- Consider dedicated link (e.g., Herelink)

#### 3. IP Address Changes

```bash
# Set static IP on companion computer
# /etc/netplan/01-network.yaml (Ubuntu)
network:
  ethernets:
    eth0:
      addresses: [192.168.1.10/24]
      gateway4: 192.168.1.1
```

## Container Connection Issues

### Symptoms

- Container can't reach host services
- MAVLink2REST unreachable from container

### Solutions

PixEagle's supported local development path runs MAVLink2REST through
`scripts/components/mavlink2rest.sh`, bound to `127.0.0.1:8088`. If you
containerize the stack, keep the same endpoint contract and make the container
networking explicit in deployment docs.

#### 1. Use Host Networking for Local Experiments

```yaml
# docker-compose.yml
services:
  pixeagle:
    network_mode: host
```

#### 2. Explicit Container Port Mapping

```yaml
services:
  pixeagle:
    ports:
      - "8088:8088"
      - "14569:14569/udp"
```

Only map the local MAVLink2REST HTTP/input ports shown above for container
experiments. Do not publish PixEagle backend `5077` from a container unless the
deployment has an explicit authenticated remote profile.

#### 3. Container DNS

```bash
# Test from container
docker exec -it <container> curl http://host.docker.internal:8088
```

## Diagnostic Commands

### Full System Check

```bash
#!/bin/bash
# connection_check.sh

echo "=== MAVLink2REST ==="
curl -s http://127.0.0.1:8088/v1/mavlink/vehicles || echo "FAILED"

echo -e "\n=== Local MAVLink UDP listeners ==="
ss -lunp | grep -E ':(14540|14569)\b' || echo "Listeners missing"

echo -e "\n=== mavlink-router ==="
pgrep -a mavlink-router || echo "Not running"

echo -e "\n=== Serial Devices ==="
ls -la /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "No devices"

echo -e "\n=== Network ==="
ss -ltnp 2>/dev/null | grep -E ':(50051|8088)\b'
```

### Log Inspection

```bash
# PixEagle logs
tail -f logs/pixeagle.log | grep -i "connection\|error\|failed"

# mavlink-router logs
journalctl -u mavlink-router -f

# MAVLink2REST wrapper process
pgrep -a mavlink2rest
```

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | PixEagle local bridge is not running | Inspect routing, then restart the owning PixEagle runtime |
| `No system found` | No MAVLink source | Check mavlink-router, SITL |
| `Permission denied` | Serial permissions | Add to dialout group |
| `Address in use` | Port conflict | Kill conflicting process |
| `Timeout` | Network/firewall | Check connectivity, firewall |

## Related Documentation

- [SITL Setup](../04-infrastructure/sitl-setup.md)
- [mavlink-router](../04-infrastructure/mavlink-router.md)
- [Hardware Connection](../04-infrastructure/hardware-connection.md)
- [Port Configuration](../04-infrastructure/port-configuration.md)
