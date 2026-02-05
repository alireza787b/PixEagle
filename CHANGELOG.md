# PixEagle Changelog

## Version 3.2.1 (2026-02-05) - Resilience & Version Consistency

### 🚀 Improvements

- Added degraded-mode startup: backend stays online when video source is unavailable.
- Added video resilience endpoints:
  - `GET /api/video/health`
  - `POST /api/video/reconnect`
- Prevented app shutdown on temporary or persistent frame loss.
- Added camera status and reconnect action in dashboard Settings.

### 🔧 Version Consistency

- Unified API-exposed project version via central `src/classes/app_version.py`.
- FastAPI app version and frontend runtime config now use the same project version.
- Dashboard package version updated to `3.2.1`.

## Version 3.2 (2025-10-10) - Professional OSD System

### 🚀 New Features

- **Aviation-Grade OSD System** - Professional HUD layouts following DJI/ArduPilot/PX4 standards
- **TrueType Font Rendering** - High-quality PIL/Pillow text rendering (4-8x better than OpenCV)
- **Resolution-Independent Scaling** - Professional 1/20th frame height sizing formula (aviation standard)
- **Real-Time Preset Switching** - API endpoint for instant preset changes without restart
- **Three Professional Presets** - Minimal (racing), Professional (default), Full Telemetry (debug)
- **RobotoMono Font Integration** - Professional monospaced font with automatic detection

### 🔧 Improvements

- **Improved Font Discovery** - Custom fonts directory checked first with proper name normalization
- **Better Text Positioning** - 8% safe zones (aviation standard) for critical data visibility
- **Visual Hierarchy** - Critical data (altitude, battery) displayed larger with plate backgrounds
- **Smaller Attitude Indicator** - Reduced from 60% to 8% screen size for professional appearance
- **Symmetric Layout Design** - Balanced left/right data organization
- **Enhanced OSD Renderer** - Immediate reinitialization when presets change via API

### 📖 Documentation

- Removed duplicate README from fonts directory (consolidated into OSD_GUIDE.md)
- Updated main README to reference comprehensive OSD documentation
- All preset files now include aviation design principles and sizing rationale

### 🐛 Bug Fixes

- Fixed custom fonts directory not stripping `-regular` suffix from font names
- Fixed preset switching requiring app restart
- Fixed font size being too small (changed from 1/30th to 1/20th of frame height)

### 🔄 Breaking Changes

None - Fully backward compatible with PixEagle 3.1

---

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
