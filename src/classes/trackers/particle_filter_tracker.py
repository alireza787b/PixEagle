# src/classes/trackers/particle_filter_tracker.py
import cv2
import numpy as np
from typing import Optional, Tuple
from classes.parameters import Parameters  # Ensure correct import path
from classes.position_estimator import PositionEstimator  # Ensure correct import path
from classes.trackers.base_tracker import BaseTracker  # Ensure correct import path
import time
#from skimage.measure import structural_similarity as ssim

class ParticleFilterTracker(BaseTracker):
    """
    Particle Filter Tracker implementation extending the BaseTracker class.
    Uses a particle filter algorithm for object tracking.
    """
    
    
    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, debug: bool = False):
        """
        Initializes the Particle Filter tracker with an optional video handler and detector.
        
        :param video_handler: Handler for video streaming and processing.
        :param detector: Object detector for initializing tracking.
        """
        super().__init__(video_handler, detector)
        self.trackerName: str = "ParticleFilter"
        self.num_particles = Parameters.PARTICLE_FILTER_NUM_PARTICLES  # e.g., 200
        self.particles = None
        self.p_weights = None
        self.ref_img = None
        self.ref_loc = None
        self.initial_bbox_width = None
        self.initial_bbox_height = None
        self.debug = debug

        # Initialize other particle filter-specific parameters here

    
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """
        Initializes the Particle Filter tracker with the provided bounding box on the given frame.
        
        :param frame: The initial video frame to start tracking.
        :param bbox: A tuple representing the bounding box (x, y, width, height).
        """
        # Extract width and height from the bbox and set them
        _, _, width, height = bbox
        self.initial_bbox_width = width
        self.initial_bbox_height = height

        # Proceed with other initialization steps...
        self.bbox = bbox  # Set the initial bounding box
        self.ref_img, self.ref_loc = self.get_ref_image(frame, bbox)
        self.initialize_particles() 

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the Particle Filter tracker with the current frame and returns the tracking success status and the new bounding box.
        
        :param frame: The current video frame.
        :return: A tuple containing the success status and the new bounding box.
        """
        dt = self.update_time()
        # Update particles based on the frame
        self.update_particle_filter(frame)
        self.frame = frame
        # Here you would determine the success and calculate the detected_bbox based on the updated particles
        # This could involve taking the average position of the particles, or the position of the most weighted particle, etc.
        success, detected_bbox = self.calculate_new_bbox()
        if self.debug:
            self.visualize_tracking(frame)
        
        if success:
            self.bbox = detected_bbox
            self.set_center(int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2))
            self.ref_img, self.ref_loc = self.get_ref_image(frame, self.bbox)

            
            if self.estimator_enabled:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(self.center)
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)
        
        return success, detected_bbox
    
    
    def calculate_new_bbox(self):
        # Calculate the weighted average position of the particles
        weighted_sum_x = np.sum([p[0] * w for p, w in zip(self.particles, self.p_weights)])
        weighted_sum_y = np.sum([p[1] * w for p, w in zip(self.particles, self.p_weights)])
        avg_x = int(weighted_sum_x / np.sum(self.p_weights))
        avg_y = int(weighted_sum_y / np.sum(self.p_weights))

        # Dynamically adjust the size of the bbox based on the spread of particles
        spread_x = np.std([p[0] for p in self.particles])
        spread_y = np.std([p[1] for p in self.particles])
        bbox_width = min(max(int(spread_x * 2), self.initial_bbox_width), self.frame.shape[1])
        bbox_height = min(max(int(spread_y * 2), self.initial_bbox_height), self.frame.shape[0])

        # Calculate the top-left corner of the bbox
        top_left_x = max(0, avg_x - bbox_width // 2)
        top_left_y = max(0, avg_y - bbox_height // 2)

        new_bbox = (top_left_x, top_left_y, bbox_width, bbox_height)
        return True, new_bbox


    # Implement additional methods specific to the Particle Filter algorithm here
    # Including get_ref_image, initialize_particles, update_particle_filter, etc.


    def initialize_particles(self):
        """
        Initializes particles around the reference location with some random spread.
        """
        # Spread range for initial particle distribution
        spread = 50  # Adjust this value based on your application's needs

        # Generate random offsets for particles around the reference location
        dx = np.random.randint(-spread, spread, self.num_particles)
        dy = np.random.randint(-spread, spread, self.num_particles)

        # Calculate particles' positions
        self.particles = np.array([self.ref_loc] * self.num_particles) + np.stack((dx, dy), axis=-1)

        # Initialize particles' weights uniformly
        self.p_weights = np.ones(self.num_particles) / self.num_particles
        if self.debug:
            print(f"Initialized {self.num_particles} particles around {self.ref_loc} with spread {spread}.")



    def make_box(img,center,w,h):
        """ utility function to calculate box corners given a center, width and height """
        
        w_half=w//2
        h_half=h//2
        x,y=center
        
        pt1=(int(x-w_half),int(y-h_half))
        pt2=(int(x+w_half),int(y-h_half))
        pt3=(int(x+w_half),int(y+h_half))
        pt4=(int(x-w_half),int(y+h_half))
        
        cv2.line(img,pt1,pt2,[0,0,255],2)
        cv2.line(img,pt2,pt3,[0,0,255],2)
        cv2.line(img,pt3,pt4,[0,0,255],2)
        cv2.line(img,pt4,pt1,[0,0,255],2)
        
        return img,pt1,pt2,pt3,pt4
                

    @staticmethod
    def get_ref_image(frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Extracts a reference image from the given frame based on the provided bounding box.
        
        :param frame: The video frame from which to extract the reference image.
        :param bbox: A tuple representing the bounding box (x, y, width, height) for the reference image.
        :return: The extracted reference image and its center coordinates.
        """
        x, y, w, h = bbox
        # Ensure the bounding box is fully within the frame dimensions
        x, y, w, h = max(0, x), max(0, y), min(w, frame.shape[1] - x), min(h, frame.shape[0] - y)
        
        # Extract the reference image from the frame using bbox coordinates
        ref_img = frame[y:y+h, x:x+w]
        
        # Calculate the center of the bounding box
        ref_center = (x + w // 2, y + h // 2)
        
        return ref_img, ref_center
        

    def calc_similarity(self,ref_img, patch, sigma, sim_type='MSE_grayscale'):
        """Calculates the similarity between the reference and the candidate patches."""
        
        # Resize patch to match the reference image size
        patch_resized = cv2.resize(patch, (ref_img.shape[1], ref_img.shape[0]))

        # Initialize variables
        sim = 0
        ranking_type = 'descending'  # Default ranking type

        # Prepare images
        color_ref_img = ref_img
        color_patch = patch_resized
        gray_ref_img = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
        gray_patch = cv2.cvtColor(patch_resized, cv2.COLOR_BGR2GRAY)

        if sim_type == 'MSE_color':
            mse = np.mean((color_ref_img - color_patch) ** 2)
            sim = np.exp(-mse / (2.0 * sigma ** 2))

        elif sim_type == 'MSE_grayscale':
            mse = np.mean((gray_ref_img - gray_patch) ** 2)
            sim = np.exp(-mse / (2.0 * sigma ** 2))

        elif sim_type in ['Covariance_color', 'Covariance_grayscale']:
            if sim_type == 'Covariance_color':
                channels_ref = cv2.split(color_ref_img)
                channels_patch = cv2.split(color_patch)
            else:
                channels_ref = [gray_ref_img]
                channels_patch = [gray_patch]

            covariances = [np.corrcoef(ch_ref.flatten(), ch_patch.flatten())[0, 1]
                        for ch_ref, ch_patch in zip(channels_ref, channels_patch)]
            sim = np.mean(covariances)

        elif sim_type.startswith('MSE_histogram'):
            if 'color' in sim_type:
                hist_ref = [cv2.calcHist([color_ref_img], [i], None, [256], [0, 256]) for i in range(3)]
                hist_patch = [cv2.calcHist([color_patch], [i], None, [256], [0, 256]) for i in range(3)]
            else:
                hist_ref = [cv2.calcHist([gray_ref_img], [0], None, [256], [0, 256])]
                hist_patch = [cv2.calcHist([gray_patch], [0], None, [256], [0, 256])]

            mse_hist = np.mean([np.mean((h_ref - h_patch) ** 2) for h_ref, h_patch in zip(hist_ref, hist_patch)])
            sim = np.exp(-mse_hist / (2.0 * sigma ** 2))

        # Add additional similarity measures if needed

        # For new similarity measures where lower values are better, adjust ranking_type
        if sim_type == 'something_new' and 'lowest value is best':
            ranking_type = 'ascending'

        #if self.debug:
        #    print(f"Similarity between ref_img and patch: {sim}, Method: {sim_type}")


        return sim, ranking_type


    def resample_particles(self, particles, p_weights):
        # Resample based on current similarity weights
        num_particles = len(p_weights)
        idx = np.random.choice(range(num_particles), size=num_particles, p=p_weights, replace=True)
        new_particles = particles[idx]

        # Introduce a small random jitter to the particles' positions to maintain diversity
        jitter = np.random.normal(0, self.initial_bbox_width * 0.05, (num_particles, 2))
        new_particles = new_particles.astype(np.float64) + jitter  # Ensure addition in float64

        # Convert back to integers for pixel coordinates
        new_particles = np.round(new_particles).astype(np.int64)

        return new_particles




    def get_patch(self,frame,w,h,x,y):
        """ extracts a new image patch from a frame based on given coordinates and patch dimensions """
        """ adjusts coordinates if off screen """
        
        #adjust edges if beyond frame
        x=x+int(w//2-x) if int(x-w//2)<0 else x
        x=x-(int(x+w//2)-len(frame[0])) if int(x+w//2)>len(frame[0]) else x
        y=y+int(h//2-y) if int(y-h//2)<0 else y
        y=y-(int(y+h//2)-len(frame)) if int(y+h//2)>len(frame) else y
        
        # calc box corners
        min_x=int(x-w//2)
        max_x=int(x+w//2)
        min_y=int(y-h//2)
        max_y=int(y+h//2)
        
        patch=frame[min_y:max_y,min_x:max_x]
        
        return patch,x,y


    def update_particle_filter(self, frame: np.ndarray):
        self.particles = self.resample_particles(self.particles, self.p_weights)

        h, w = self.ref_img.shape[:2]
        sims = np.zeros(self.num_particles)
        new_particles = np.zeros_like(self.particles)
        
        for i, p in enumerate(self.particles):
            motion_sigma = Parameters.PARTICLE_FILTER_SIGMA_MOVE_NEAR if self.p_weights[i] > np.mean(self.p_weights) else Parameters.PARTICLE_FILTER_SIGMA_MOVE_FAR
            x, y = p[0] + np.random.normal(0, motion_sigma), p[1] + np.random.normal(0, motion_sigma)
            
            x, y = np.clip(x, 0, frame.shape[1] - 1), np.clip(y, 0, frame.shape[0] - 1)
            
            patch, px, py = self.get_patch(frame, w, h, x, y)
            sim = self.calc_similarity(self.ref_img, patch, Parameters.PARTICLE_FILTER_SIGMA, Parameters.PARTICLE_FILTER_SIMILARITY_MEASURE)[0]
            sims[i] = sim
            new_particles[i] = [px, py]

        sims = np.exp(sims - np.max(sims))  # Apply softmax-like normalization
        self.p_weights = sims / np.sum(sims)
        self.particles = new_particles

       


        def reset_particle_filter(frame,ref_img,particles,p_weights,ranking_type):
            """ extract new reference image based on new estimated location """
            
            # best smallest/highest value should depend on comparison metric
            if ranking_type=='descending':
                idx=np.argsort(p_weights)[::-1][0]
            else:
                idx=np.argsort(p_weights)[0]
                
            # select coords based on top particle
            x_best=particles[idx,0]
            y_best=particles[idx,1]
            
            # make new ref_img, with tracking window included
            h,w=ref_img.shape[:2]
            
            min_x=int(x_best-w//2)
            max_x=int(x_best+w//2)
            min_y=int(y_best-h//2)
            max_y=int(y_best+h//2)
            
            new_particles=particles.copy()
            for i,p in enumerate(particles):
                new_particles[i]=[x_best,y_best]
            
            # extract new ref image
            new_ref_img=frame[min_y:max_y,min_x:max_x]
            
            return new_ref_img,new_particles,(x_best,y_best)


    def draw_particles(frame,particles):
        """ draw dots to represent particle locations in the image """
        
        for p in particles:
            cv2.circle(frame,(int(p[0]),int(p[1])),1,(0,0,255),1)
        
        return frame

    
    def visualize_tracking(self, frame):
        for p in self.particles:
            cv2.circle(frame, (int(p[0]), int(p[1])), 2, (0, 255, 0), -1)
        if self.bbox:
            x, y, w, h = self.bbox
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow(Parameters.FRAME_TITLE, frame)
        cv2.waitKey(1)


    def calculate_particle_spread(self):
        if self.particles is not None:
            particle_positions = np.array(self.particles)
            x_spread = np.std(particle_positions[:, 0])
            y_spread = np.std(particle_positions[:, 1])
            return x_spread + y_spread
        return 0
