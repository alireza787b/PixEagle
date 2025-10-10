# PixEagle Changelog

## Version 3.1 (2025-10-09) - SmartTracker Enhanced

### 🚀 New Features

- **Multi-Tracker System** - Choose between 4 tracking modes (ByteTrack, BoT-SORT, BoT-SORT+ReID, Custom ReID)
- **Ultralytics BoT-SORT Integration** - Native ReID support for professional-grade tracking
- **Custom Lightweight ReID** - Offline re-identification for embedded systems and air-gapped drones
- **Configurable Feature Extraction** - HOG and histogram parameters now fully configurable
- **Performance Profiling** - Built-in profiling system for appearance model metrics
- **Automatic Version Detection** - Graceful fallback based on Ultralytics version

### 🔧 Improvements

- **Enhanced Frame Validation** - Robust error handling with minimum ROI size checks
- **Tracker-Agnostic Architecture** - TrackingStateManager works with any Ultralytics tracker
- **Better Error Messages** - Clear logging and troubleshooting information
- **Configuration Consolidation** - All tracker settings in config_default.yaml following PixEagle patterns

### 📖 Documentation

- **New: Complete SmartTracker Guide** - Comprehensive documentation for users and developers
- **Updated README** - Clear SmartTracker introduction with quick start examples
- **Performance Benchmarks** - FPS and accuracy comparisons for all tracker modes
- **Decision Guide** - Help users choose the right tracker for their scenario

### 🐛 Bug Fixes

- Fixed invalid YOLO arguments error (only persist/verbose passed to model.track)
- Fixed attribute error in get_output() method (tracker_type vs tracker_type_str)
- Removed unused separate tracker YAML files
- Cleaned up gitignore entries

### 🔄 Breaking Changes

None - Fully backward compatible with PixEagle 3.0

---

## Version 3.0 (2025-01-XX) - Smart Tracker Introduction

- Initial SmartTracker implementation with YOLO integration
- GPU/CPU support with automatic fallback
- Web dashboard revamp
- Schema-aware architecture
- Service management system

---

## Version 2.0 (2024-XX-XX)

- Classic tracker improvements (CSRT, KCF)
- MAVLink integration enhancements
- Follow mode implementations

---

## Version 1.0 (Initial Release)

- Basic tracking and following functionality
- PX4 integration
- Web dashboard
