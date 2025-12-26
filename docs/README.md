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
| [Configuration Guide](CONFIGURATION.md) | All configuration options |
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and solutions |
| [Windows SITL Setup](WINDOWS_SITL_XPLANE.md) | X-Plane simulation on Windows |

---

## Feature Guides

| Guide | Description |
|-------|-------------|
| [SmartTracker Guide](SMART_TRACKER_GUIDE.md) | Complete SmartTracker setup and configuration |
| [OSD Guide](OSD_GUIDE.md) | Aviation-grade OSD with presets and API control |
| [OpenCV GStreamer](OPENCV_GSTREAMER.md) | Building OpenCV with GStreamer support |
| [Gimbal Simulator](gimbal_simulator.md) | Testing gimbal functionality |
| [Tracker & Follower Schema](Tracker_and_Follower_Schema_Developer_Guide.md) | Schema-driven architecture guide |

---

## Follower System

Comprehensive documentation for the autonomous following system.

| Guide | Description |
|-------|-------------|
| [Follower Overview](followers/README.md) | Complete follower system guide |
| [Architecture](followers/01-architecture/README.md) | System design and components |
| [Follower Reference](followers/02-reference/README.md) | All 10 follower implementations |
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
| [Gimbal Implementation Plan](developers/GIMBAL_FOLLOWER_IMPLEMENTATION_PLAN.md) | Gimbal follower architecture |
| [Gimbal Vector Implementation](developers/GIMBAL_VECTOR_BODY_IMPLEMENTATION_SUMMARY.md) | Body-frame vector control |
| [Velocity Research](developers/FORWARD_VELOCITY_RESEARCH_GUIDE.md) | Forward velocity control research |
| [3D Validation Report](developers/position_3d_validation_test_report.md) | Position 3D validation testing |

---

## Internal Documents

These documents are for internal reference during development.

| Document | Description |
|----------|-------------|
| [Configuration Refactoring](CONFIGURATION_REFACTORING_GUIDE.md) | Config system refactoring notes |
| [Conflict Check Report](CONFLICT_CHECK_REPORT.md) | Merge conflict resolution report |
| [SmartTracker Improvements](SMARTTRACKER_IMPROVEMENTS.md) | Planned SmartTracker enhancements |
| [YOLO Download Improvements](YOLO_MODEL_DOWNLOAD_IMPROVEMENTS.md) | YOLO model management improvements |
| [YOLO Download UX](YOLO_MODEL_DOWNLOAD_USER_EXPERIENCE.md) | YOLO download user experience |

---

## Configuration Reference

Key configuration files:

- `configs/config.yaml` - Main application configuration
- `configs/config_schema.yaml` - Configuration schema definitions
- `dashboard/.env` - Dashboard environment variables

---

## Need Help?

- **Issues**: [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- **Discussions**: [GitHub Discussions](https://github.com/alireza787b/PixEagle/discussions)
- **Videos**: [YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)
