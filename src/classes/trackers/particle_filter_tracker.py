# src/classes/trackers/particle_filter_tracker.py

"""
ParticleFilterTracker Module
----------------------------

This module implements the `ParticleFilterTracker` class, a concrete tracker that uses an enhanced Particle Filter algorithm for object tracking.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: October 2024
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The `ParticleFilterTracker` class extends the `BaseTracker` and specializes in object tracking using a particle filter with advanced techniques to handle real-world challenges.

Key Enhancements:
-----------------
- Enhanced Motion Model with Acceleration
- Particle Diversity Maintenance
- Contextual Information Usage
- Failure Recovery Mechanism
- Optimized Resampling (Stratified Resampling)
- Efficient Computations with Vectorization

Usage:
------
The `ParticleFilterTracker` can be instantiated via the `tracker_factory.py` and requires a video handler, detector, and app controller.

Example:
```python
tracker = ParticleFilterTracker(video_handler, detector, app_controller)
tracker.start_tracking(initial_frame, initial_bbox)
```

Dependencies:
-------------
- NumPy
- OpenCV

Notes:
------
- Appearance-related methods have been moved to the detector class.
- Confidence calculation is standardized using the `compute_confidence` method in the base tracker.

"""

import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker

class ParticleFilterTracker(BaseTracker):
    """
    ParticleFilterTracker Class

    Implements object tracking using an enhanced Particle Filter algorithm, extending the `BaseTracker`.
    """

    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, app_controller: Optional[object] = None):
        """
        Initializes the ParticleFilterTracker with a video handler, detector, and app controller.

        Args:
            video_handler (Optional[object]): Handler for video streaming and processing.
            detector (Optional[object]): Object detector for appearance-based methods.
            app_controller (Optional[object]): Reference to the main application controller.
        """
        super().__init__(video_handler, detector, app_controller)
        self.trackerName: str = "ParticleFilter"
        self.num_particles = int(Parameters.PF_NUM_PARTICLES)
        self.state_dim = 6  # State vector: [x, y, vx, vy, ax, ay]
        self.particles = None
        self.weights = None
        # Correctly initialize the effective particle number threshold
        self.effective_particle_num_threshold = float(self.get_effective_particle_num_threshold())
        if self.position_estimator:
            self.position_estimator.reset()

    def get_effective_particle_num_threshold(self) -> float:
        """
        Calculates the effective particle number threshold.

        Returns:
            float: The effective particle number threshold.
        """
        return Parameters.PF_EFFECTIVE_PARTICLE_NUM_THRESHOLD * Parameters.PF_NUM_PARTICLES

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Initializes the particle filter with the provided bounding box on the given frame.

        Args:
            frame (np.ndarray): The initial video frame.
            bbox (Tuple[int, int, int, int]): A tuple representing the bounding box (x, y, width, height).
        """
        logging.info(f"Initializing {self.trackerName} tracker with bbox: {bbox}")
        x, y, w, h = bbox
        center_x = x + w / 2
        center_y = y + h / 2

        # Initialize particles around the initial position with some noise
        self.particles = np.empty((self.num_particles, self.state_dim))
        self.particles[:, 0] = np.random.normal(center_x, Parameters.PF_INIT_POS_STD, self.num_particles)
        self.particles[:, 1] = np.random.normal(center_y, Parameters.PF_INIT_POS_STD, self.num_particles)
        self.particles[:, 2] = np.random.normal(0, Parameters.PF_INIT_VEL_STD, self.num_particles)
        self.particles[:, 3] = np.random.normal(0, Parameters.PF_INIT_VEL_STD, self.num_particles)
        self.particles[:, 4] = np.random.normal(0, Parameters.PF_INIT_ACC_STD, self.num_particles)
        self.particles[:, 5] = np.random.normal(0, Parameters.PF_INIT_ACC_STD, self.num_particles)

        # Initialize weights uniformly
        self.weights = np.ones(self.num_particles) / self.num_particles

        # Initialize appearance models using the detector
        if self.detector:
            self.detector.initial_template = frame[y:y+h, x:x+w].copy()
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        self.prev_center = None  # Reset previous center
        self.last_update_time = time.time()

        # Set initial bbox and center
        self.bbox = bbox
        self.set_center((int(center_x), int(center_y)))
        self.normalize_bbox()
        self.center_history.append(self.center)

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the particle filter with the current frame and returns the tracking success status and the new bounding box.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: A tuple containing the success status and the new bounding box.
        """
        dt = self.update_time()

        # Propagate particles
        self.propagate_particles(dt)

        # Compute weights based on appearance likelihood
        self.compute_weights(frame)

        # Check if weights are all zeros
        if np.sum(self.weights) == 0:
            logging.warning("All particle weights are zero. Tracking failed.")
            success = False
            # self.update_estimator_without_measurement()
            return success, self.bbox

        # Normalize weights
        self.weights /= np.sum(self.weights)

        # Estimate state
        estimated_state = self.estimate_state()

        # Update bbox and center
        estimated_center = (int(estimated_state[0]), int(estimated_state[1]))
        self.prev_center = self.center
        self.set_center(estimated_center)
        self.bbox = self.get_bbox_from_state(estimated_state)
        self.normalize_bbox()
        self.center_history.append(self.center)

        # Update adaptive appearance model using the detector
        if self.detector:
            current_features = self.detector.extract_features(frame, self.bbox)
            self.detector.adaptive_features = (1 - Parameters.PF_APPEARANCE_LEARNING_RATE) * self.detector.adaptive_features + \
                                      Parameters.PF_APPEARANCE_LEARNING_RATE * current_features

        # Resample particles
        self.resample_particles()

        # Maintain particle diversity
        effective_particle_num = self.compute_effective_particle_number()
        # Ensure both variables are floats
        effective_particle_num = float(effective_particle_num)
        threshold = float(self.effective_particle_num_threshold)
        if effective_particle_num < threshold:
            self.inject_random_particles()

        # Compute confidence scores
        self.compute_confidence(frame)
        total_confidence = self.get_confidence()
        logging.debug(f"Total Confidence: {total_confidence}")

        # Perform consistency checks
        success = True
        if self.confidence < Parameters.CONFIDENCE_THRESHOLD:
            logging.warning("Tracking failed due to low confidence.")
            success = False

        if success:
            if self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)
        else:
            logging.warning("Tracking update failed.")
            # Optionally, handle estimator update without measurement
            self.update_estimator_without_measurement()

        return success, self.bbox

    def propagate_particles(self, dt: float) -> None:
        """
        Propagates particles based on the enhanced motion model with acceleration.

        Args:
            dt (float): Time delta since the last update.
        """
        # Add process noise
        noise_pos = np.random.normal(0, Parameters.PF_POS_STD, (self.num_particles, 2))
        noise_vel = np.random.normal(0, Parameters.PF_VEL_STD, (self.num_particles, 2))
        noise_acc = np.random.normal(0, Parameters.PF_ACC_STD, (self.num_particles, 2))

        # Update positions
        self.particles[:, 0] += self.particles[:, 2] * dt + 0.5 * self.particles[:, 4] * dt**2 + noise_pos[:, 0]
        self.particles[:, 1] += self.particles[:, 3] * dt + 0.5 * self.particles[:, 5] * dt**2 + noise_pos[:, 1]

        # Update velocities
        self.particles[:, 2] += self.particles[:, 4] * dt + noise_vel[:, 0]
        self.particles[:, 3] += self.particles[:, 5] * dt + noise_vel[:, 1]

        # Update accelerations
        self.particles[:, 4] += noise_acc[:, 0]
        self.particles[:, 5] += noise_acc[:, 1]

        # Ensure particles are within frame bounds
        frame_width = self.video_handler.width
        frame_height = self.video_handler.height
        self.particles[:, 0] = np.clip(self.particles[:, 0], 0, frame_width - 1)
        self.particles[:, 1] = np.clip(self.particles[:, 1], 0, frame_height - 1)

    def compute_weights(self, frame: np.ndarray) -> None:
        """
        Computes weights for each particle based on combined appearance likelihood.

        Args:
            frame (np.ndarray): The current video frame.
        """
        # Precompute common variables
        half_width = int(self.bbox[2] / 2)
        half_height = int(self.bbox[3] / 2)
        frame_height, frame_width = frame.shape[:2]

        # Vectorized computation
        xs = self.particles[:, 0].astype(int)
        ys = self.particles[:, 1].astype(int)
        x1s = np.clip(xs - half_width, 0, frame_width - 1)
        y1s = np.clip(ys - half_height, 0, frame_height - 1)
        x2s = np.clip(xs + half_width, 0, frame_width - 1)
        y2s = np.clip(ys + half_height, 0, frame_height - 1)

        likelihoods = np.zeros(self.num_particles)

        for i in range(self.num_particles):
            x1, y1, x2, y2 = x1s[i], y1s[i], x2s[i], y2s[i]
            particle_bbox = (x1, y1, x2 - x1, y2 - y1)
            if x1 >= x2 or y1 >= y2:
                likelihoods[i] = 0
                continue

            # Compute appearance likelihood using detector
            if self.detector:
                particle_features = self.detector.extract_features(frame, particle_bbox)
                color_similarity = cv2.compareHist(self.detector.adaptive_features, particle_features, cv2.HISTCMP_BHATTACHARYYA)
                roi = frame[y1:y2, x1:x2]
                edge_similarity = self.detector.compute_edge_similarity(self.detector.initial_template, roi)
                total_similarity = (Parameters.PF_COLOR_WEIGHT * color_similarity +
                                    Parameters.PF_EDGE_WEIGHT * edge_similarity)
                likelihoods[i] = np.exp(-Parameters.PF_APPEARANCE_LIKELIHOOD_SCALE * total_similarity)
            else:
                likelihoods[i] = 1.0  # If no detector, assign equal weight

        self.weights = likelihoods

    def resample_particles(self) -> None:
        """
        Resamples particles based on their weights using stratified resampling.
        """
        cumulative_sum = np.cumsum(self.weights)
        cumulative_sum[-1] = 1.0  # Ensure sum is exactly one

        positions = (np.arange(self.num_particles) + np.random.uniform(0, 1)) / self.num_particles

        indexes = np.zeros(self.num_particles, dtype=int)
        i, j = 0, 0
        while i < self.num_particles:
            if positions[i] < cumulative_sum[j]:
                indexes[i] = j
                i += 1
            else:
                j += 1
        self.particles = self.particles[indexes]
        self.weights = np.ones(self.num_particles) / self.num_particles

    def estimate_state(self) -> np.ndarray:
        """
        Estimates the state from particles and weights.

        Returns:
            np.ndarray: The estimated state vector.
        """
        estimated_state = np.average(self.particles, weights=self.weights, axis=0)
        return estimated_state

    def compute_effective_particle_number(self) -> float:
        """
        Computes the effective number of particles to assess diversity.

        Returns:
            float: The effective number of particles.
        """
        return 1.0 / np.sum(self.weights ** 2)

    def inject_random_particles(self) -> None:
        """
        Injects random particles to maintain diversity.

        This helps prevent particle degeneracy.
        """
        num_random_particles = int(self.num_particles * Parameters.PF_RANDOM_PARTICLE_RATIO)
        random_indexes = np.random.choice(self.num_particles, num_random_particles, replace=False)

        # Re-initialize selected particles
        self.particles[random_indexes, 0] = np.random.uniform(0, self.video_handler.width, num_random_particles)
        self.particles[random_indexes, 1] = np.random.uniform(0, self.video_handler.height, num_random_particles)
        self.particles[random_indexes, 2:] = 0  # Reset velocities and accelerations

    def get_bbox_from_state(self, state: np.ndarray) -> Tuple[int, int, int, int]:
        """
        Constructs a bounding box from the state vector.

        Args:
            state (np.ndarray): The state vector.

        Returns:
            Tuple[int, int, int, int]: The bounding box (x, y, w, h).
        """
        x_center, y_center = state[0], state[1]
        w, h = self.bbox[2], self.bbox[3]
        x = int(x_center - w / 2)
        y = int(y_center - h / 2)
        return (x, y, int(w), int(h))

    def update_estimator_without_measurement(self) -> None:
        """
        Updates the position estimator when no measurement is available.
        """
        dt = self.update_time()
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)
            logging.debug(f"Estimated position (without measurement): {estimated_position}")
        else:
            logging.warning("Estimator is not enabled or not initialized.")

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """
        Gets the current estimated position from the estimator.

        Returns:
            Optional[Tuple[float, float]]: The estimated (x, y) position or None if unavailable.
        """
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None
