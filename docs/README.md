# PixEagle Documentation

Welcome to the PixEagle documentation. This guide will help you find the information you need.

## Quick Links

| Document | Description |
|----------|-------------|
| [Main README](../README.md) | Quick start and overview |
| [CHANGELOG](../CHANGELOG.md) | Version history and updates |

---

## Getting Started

| Guide | Description |
|-------|-------------|
| [Installation Guide](INSTALLATION.md) | Detailed installation instructions |
| [Local Follower Test](drone-interface/06-development/follower-command-preview.md) | Included-video tracker/follower test with no PX4/MAVSDK publication |
| [Model Setup](MODEL_SETUP.md) | Trusted local detect/OBB model setup and readiness proof |
| [Setup Profiles](setup/setup-profiles.md) | Local dev, QGC field video, lab browser, and guarded production reverse-proxy profiles |
| [Production Remote Runbook](setup/production-remote-reverse-proxy.md) | Linux credentials, nginx/TLS boundary, firewall, evidence, and rollback |
| [Binary Download Policy](setup/binary-download-policy.md) | Pinned MAVSDK/MAVLink2REST assets, SHA-256 verification, overrides, and provenance |
| [Configuration Guide](CONFIGURATION.md) | All configuration options |
| [Config Sync](CONFIG_SYNC.md) | Versioned defaults reconciliation, exact retirements, preview/apply, and rollback |
| [Service Management](SERVICE_MANAGEMENT.md) | systemd + tmux production operations |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions |
| [Known Issues / TODO](KNOWN_ISSUES.md) | Verified open issues being tracked |
| [Windows/X-Plane SITL Disposition](WINDOWS_SITL_XPLANE.md) | Unmaintained path warning and requirements for any future maintained workflow |

---

## Feature Guides

| Guide | Description |
|-------|-------------|
| [OSD Guide](OSD_GUIDE.md) | Aviation-grade OSD with presets and API control |
| [OpenCV GStreamer](OPENCV_GSTREAMER.md) | Building OpenCV with GStreamer support |
| [Gimbal Simulator](gimbal_simulator.md) | Testing gimbal functionality |
| [Companion Runtime Contract](architecture/companion-runtime-contract.md) | Sidecar ownership, auth, profile, secret, version, and evidence boundaries |
| [API Exposure Boundary](apis/api-exposure-boundary.md) | Backend bind, CORS, route exposure, and production remote evidence boundary |
| [API Security Policy](apis/api-security-policy.md) | Default-deny route classification, scopes, CSRF, audit treatment, and enforcement roadmap |

---

## Tracker System

Comprehensive documentation for the object tracking system.

| Guide | Description |
|-------|-------------|
| [Tracker Overview](trackers/README.md) | Complete tracker system guide |
| [Architecture](trackers/01-architecture/README.md) | BaseTracker, factory, TrackerOutput |
| [Tracker Reference](trackers/02-reference/README.md) | CSRT, KCF, dlib, Gimbal, SmartTracker |
| [AI Concepts](trackers/03-ai-concepts/README.md) | YOLO, ByteTrack, motion prediction |
| [Configuration](trackers/04-configuration/README.md) | Schema, parameters, tuning |
| [Development Guide](trackers/05-development/README.md) | Creating custom trackers |
| [Integration](trackers/06-integration/README.md) | Follower and external system integration |

---

## Follower System

Comprehensive documentation for the autonomous following system.

| Guide | Description |
|-------|-------------|
| [Follower Overview](followers/README.md) | Complete follower system guide |
| [Architecture](followers/01-architecture/README.md) | System design and components |
| [Follower Reference](followers/02-reference/README.md) | Active follower implementations |
| [GNC Concepts](followers/03-gnc-concepts/README.md) | PN, L1, TECS, PID algorithms |
| [Configuration](followers/04-configuration/README.md) | Parameters, schema, tuning |
| [Development Guide](followers/05-development/README.md) | Creating new followers |
| [Safety System](followers/06-safety/README.md) | SafetyManager and limits |
| [Integration](followers/07-integration/README.md) | Tracker and MAVLink integration |

---

## Developer Documentation

Internal development guides and technical references.

| Guide | Description |
|-------|-------------|
| [Schema Development Guide](developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md) | Schema-driven development patterns |
| [Gimbal Vector Reference](followers/02-reference/gm-velocity-vector.md) | Current `gm_velocity_vector` follower |
| [Velocity Research](developers/FORWARD_VELOCITY_RESEARCH_GUIDE.md) | Forward velocity control research |
| [3D Validation Report](developers/position_3d_validation_test_report.md) | Position 3D validation testing |

---

## Configuration Reference

Key configuration files:

- `configs/config_default.yaml` - Checked-in runtime default configuration
- `configs/config.yaml` - Optional local override configuration created only when needed
- `configs/config_schema.yaml` - Configuration schema definitions
- `dashboard/.env` - Dashboard environment variables

---

## Need Help?

- **Issues**: [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- **Discussions**: [GitHub Discussions](https://github.com/alireza787b/PixEagle/discussions)
- **Videos**: [YouTube Playlist](https://www.youtube.com/playlist?list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)
