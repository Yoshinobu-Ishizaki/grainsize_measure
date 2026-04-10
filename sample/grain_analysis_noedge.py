import cv2
import numpy as np
import matplotlib.pyplot as plt
from skimage import filters, segmentation, measure, morphology
from skimage.feature import peak_local_maxima
from scipy import ndimage
import pandas as pd
from matplotlib.patches import Rectangle
import seaborn as sns

class GrainAnalyzer:
    def __init__(self, image_path):
        """
        Initialize the grain analyzer with an SEM image.
        
        Parameters:
        image_path (str): Path to the SEM image file
        """
        self.image_path = image_path
        self.original_image = None
        self.processed_image = None
        self.labeled_grains = None
        self.grain_properties = None
        
    def load_image(self):
        """Load and convert image to grayscale."""
        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise ValueError(f"Could not load image from {self.image_path}")
        
        # Convert to grayscale
        if len(self.original_image.shape) == 3:
            self.processed_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2GRAY)
        else:
            self.processed_image = self.original_image.copy()
        
        print(f"Image loaded: {self.processed_image.shape}")
        
    def preprocess_image(self, gaussian_sigma=1.0, contrast_factor=1.2):
        """
        Preprocess the image for better segmentation.
        
        Parameters:
        gaussian_sigma (float): Standard deviation for Gaussian blur
        contrast_factor (float): Contrast enhancement factor
        """
        # Apply Gaussian blur to reduce noise
        self.processed_image = filters.gaussian(self.processed_image, sigma=gaussian_sigma)
        
        # Enhance contrast
        self.processed_image = np.clip(self.processed_image * contrast_factor, 0, 255).astype(np.uint8)
        
        # Apply histogram equalization for better contrast
        self.processed_image = cv2.equalizeHist(self.processed_image)
        
        print("Image preprocessing completed")
    
    def segment_grains(self, threshold_method='otsu', min_distance=10):
        """
        Segment grains using watershed algorithm.
        
        Parameters:
        threshold_method (str): Thresholding method ('otsu', 'adaptive', or 'manual')
        min_distance (int): Minimum distance between watershed markers
        """
        # Apply thresholding
        if threshold_method == 'otsu':
            threshold = filters.threshold_otsu(self.processed_image)
            binary = self.processed_image > threshold
        elif threshold_method == 'adaptive':
            binary = filters.threshold_local(self.processed_image, block_size=35, offset=10)
            binary = self.processed_image > binary
        else:  # manual threshold
            threshold = 128  # You can adjust this value
            binary = self.processed_image > threshold
        
        # Clean up the binary image
        binary = morphology.binary_closing(binary, morphology.disk(2))
        binary = morphology.binary_opening(binary, morphology.disk(1))
        
        # Calculate distance transform
        distance = ndimage.distance_transform_edt(binary)
        
        # Find local maxima as markers for watershed
        coordinates = peak_local_maxima(distance, min_distance=min_distance, threshold_abs=0.3*distance.max())
        markers = np.zeros_like(distance, dtype=bool)
        markers[tuple(coordinates.T)] = True
        markers = measure.label(markers)
        
        # Apply watershed
        self.labeled_grains = segmentation.watershed(-distance, markers, mask=binary)
        
        print(f"Segmentation completed: {len(np.unique(self.labeled_grains)) - 1} grains detected")
    
    def calculate_grain_properties(self, min_area=50, exclude_edge_grains=True, edge_buffer=5):
        """
        Calculate properties for each grain.
        
        Parameters:
        min_area (int): Minimum area threshold to filter small artifacts
        exclude_edge_grains (bool): Whether to exclude grains touching image edges
        edge_buffer (int): Pixel buffer from edge to consider as "edge-touching"
        """
        # Calculate region properties
        properties = measure.regionprops(self.labeled_grains)
        
        # Get image dimensions
        height, width = self.labeled_grains.shape
        
        # Filter out small regions and optionally edge-touching grains
        filtered_properties = []
        edge_excluded_count = 0
        
        for prop in properties:
            # Skip if too small
            if prop.area < min_area:
                continue
            
            # Check if grain touches image edges
            if exclude_edge_grains:
                bbox = prop.bbox  # (min_row, min_col, max_row, max_col)
                min_row, min_col, max_row, max_col = bbox
                
                # Check if bounding box touches edges (with buffer)
                touches_edge = (
                    min_row <= edge_buffer or  # Top edge
                    min_col <= edge_buffer or  # Left edge
                    max_row >= height - edge_buffer or  # Bottom edge
                    max_col >= width - edge_buffer  # Right edge
                )
                
                if touches_edge:
                    edge_excluded_count += 1
                    continue
            
            filtered_properties.append(prop)
        
        # Extract relevant measurements
        grain_data = []
        for prop in filtered_properties:
            grain_data.append({
                'grain_id': prop.label,
                'area_pixels': prop.area,
                'centroid_x': prop.centroid[1],
                'centroid_y': prop.centroid[0],
                'major_axis_length': prop.major_axis_length,
                'minor_axis_length': prop.minor_axis_length,
                'eccentricity': prop.eccentricity,
                'solidity': prop.solidity,
                'equivalent_diameter': prop.equivalent_diameter,
                'perimeter': prop.perimeter
            })
        
        self.grain_properties = pd.DataFrame(grain_data)
        
        # Print summary
        total_detected = len(properties)
        small_filtered = total_detected - len(filtered_properties) - edge_excluded_count
        final_count = len(self.grain_properties)
        
        print(f"Grain filtering summary:")
        print(f"  Total detected: {total_detected}")
        print(f"  Too small (< {min_area} pixels): {small_filtered}")
        if exclude_edge_grains:
            print(f"  Edge-touching grains excluded: {edge_excluded_count}")
        print(f"  Final grain count: {final_count}")
        
        return self.grain_properties
    
    def get_area_statistics(self):
        """Calculate and return area distribution statistics."""
        if self.grain_properties is None:
            raise ValueError("Grain properties not calculated yet. Run calculate_grain_properties() first.")
        
        areas = self.grain_properties['area_pixels']
        
        stats = {
            'count': len(areas),
            'mean': areas.mean(),
            'median': areas.median(),
            'std': areas.std(),
            'min': areas.min(),
            'max': areas.max(),
            'q25': areas.quantile(0.25),
            'q75': areas.quantile(0.75)
        }
        
        return stats
    
    def visualize_results(self, save_path=None, show_edge_exclusion=True):
        """
        Create comprehensive visualization of the analysis results.
        
        Parameters:
        save_path (str): Optional path to save the figure
        show_edge_exclusion (bool): Whether to highlight excluded edge regions
        """
        if self.grain_properties is None:
            raise ValueError("Grain properties not calculated yet.")
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('SEM Grain Analysis Results', fontsize=16, fontweight='bold')
        
        # 1. Original image
        axes[0, 0].imshow(cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB))
        axes[0, 0].set_title('Original SEM Image')
        axes[0, 0].axis('off')
        
        # 2. Processed image
        axes[0, 1].imshow(self.processed_image, cmap='gray')
        axes[0, 1].set_title('Processed Image')
        axes[0, 1].axis('off')
        
        # 3. Segmented grains with edge exclusion visualization
        segmented_display = self.labeled_grains.copy()
        
        # Create a mask for accepted grains
        accepted_grain_ids = set(self.grain_properties['grain_id'])
        accepted_mask = np.isin(self.labeled_grains, list(accepted_grain_ids))
        
        # Create visualization showing accepted vs excluded grains
        visualization = np.zeros_like(self.labeled_grains)
        visualization[accepted_mask] = self.labeled_grains[accepted_mask]
        
        axes[0, 2].imshow(visualization, cmap='nipy_spectral')
        axes[0, 2].set_title(f'Analyzed Grains (n={len(self.grain_properties)})')
        
        # Add edge exclusion zone visualization
        if show_edge_exclusion:
            height, width = self.labeled_grains.shape
            edge_buffer = 5  # Should match the buffer used in calculate_grain_properties
            
            # Draw edge exclusion zone
            rect_top = Rectangle((0, 0), width, edge_buffer, 
                               linewidth=2, edgecolor='red', facecolor='red', alpha=0.3)
            rect_bottom = Rectangle((0, height-edge_buffer), width, edge_buffer, 
                                  linewidth=2, edgecolor='red', facecolor='red', alpha=0.3)
            rect_left = Rectangle((0, 0), edge_buffer, height, 
                                linewidth=2, edgecolor='red', facecolor='red', alpha=0.3)
            rect_right = Rectangle((width-edge_buffer, 0), edge_buffer, height, 
                                 linewidth=2, edgecolor='red', facecolor='red', alpha=0.3)
            
            axes[0, 2].add_patch(rect_top)
            axes[0, 2].add_patch(rect_bottom)
            axes[0, 2].add_patch(rect_left)
            axes[0, 2].add_patch(rect_right)
        
        axes[0, 2].axis('off')
        
        # 4. Area distribution histogram
        areas = self.grain_properties['area_pixels']
        axes[1, 0].hist(areas, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        axes[1, 0].set_xlabel('Grain Area (pixels)')
        axes[1, 0].set_ylabel('Frequency')
        axes[1, 0].set_title('Grain Area Distribution')
        axes[1, 0].grid(True, alpha=0.3)
        
        # 5. Cumulative distribution
        sorted_areas = np.sort(areas)
        cumulative = np.arange(1, len(sorted_areas) + 1) / len(sorted_areas)
        axes[1, 1].plot(sorted_areas, cumulative, 'b-', linewidth=2)
        axes[1, 1].set_xlabel('Grain Area (pixels)')
        axes[1, 1].set_ylabel('Cumulative Probability')
        axes[1, 1].set_title('Cumulative Area Distribution')
        axes[1, 1].grid(True, alpha=0.3)
        
        # 6. Statistics summary
        stats = self.get_area_statistics()
        axes[1, 2].axis('off')
        stats_text = f"""
        Statistics Summary
        ─────────────────
        Count: {stats['count']}
        Mean: {stats['mean']:.1f} pixels
        Median: {stats['median']:.1f} pixels
        Std Dev: {stats['std']:.1f} pixels
        Min: {stats['min']:.1f} pixels
        Max: {stats['max']:.1f} pixels
        Q25: {stats['q25']:.1f} pixels
        Q75: {stats['q75']:.1f} pixels
        
        Note: Edge grains excluded
        """
        axes[1, 2].text(0.1, 0.9, stats_text, transform=axes[1, 2].transAxes, 
                        fontsize=12, verticalalignment='top', fontfamily='monospace')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Visualization saved to {save_path}")
        
        plt.show()
    
    def save_results(self, csv_path='grain_analysis_results.csv'):
        """Save grain properties to CSV file."""
        if self.grain_properties is None:
            raise ValueError("Grain properties not calculated yet.")
        
        self.grain_properties.to_csv(csv_path, index=False)
        print(f"Results saved to {csv_path}")
    
    def analyze_complete(self, image_path=None, **kwargs):
        """
        Complete analysis pipeline.
        
        Parameters:
        image_path (str): Path to image file (optional if already set)
        **kwargs: Additional parameters for processing steps
        """
        if image_path:
            self.image_path = image_path
        
        # Execute full pipeline
        self.load_image()
        self.preprocess_image(**kwargs.get('preprocess_params', {}))
        self.segment_grains(**kwargs.get('segment_params', {}))
        self.calculate_grain_properties(**kwargs.get('properties_params', {}))
        
        # Display results
        self.visualize_results(kwargs.get('save_path'))
        
        # Save results
        if kwargs.get('save_csv', True):
            self.save_results(kwargs.get('csv_path', 'grain_analysis_results.csv'))
        
        return self.grain_properties


# Example usage
if __name__ == "__main__":
    # Initialize analyzer
    analyzer = GrainAnalyzer("your_sem_image.jpg")  # Replace with your image path
    
    # Method 1: Step-by-step analysis
    try:
        analyzer.load_image()
        analyzer.preprocess_image(gaussian_sigma=1.0, contrast_factor=1.2)
        analyzer.segment_grains(threshold_method='otsu', min_distance=15)
        properties = analyzer.calculate_grain_properties(min_area=50)
        
        # Display statistics
        stats = analyzer.get_area_statistics()
        print("\nGrain Area Statistics:")
        print("-" * 30)
        for key, value in stats.items():
            print(f"{key.capitalize()}: {value:.2f}")
        
        # Visualize results
        analyzer.visualize_results()
        
        # Save results
        analyzer.save_results()
        
    except Exception as e:
        print(f"Error: {e}")
        print("Please make sure to replace 'your_sem_image.jpg' with the actual path to your SEM image.")
    
    # Method 2: Complete analysis in one call
    # analyzer.analyze_complete(
    #     image_path="your_sem_image.jpg",
    #     preprocess_params={'gaussian_sigma': 1.0, 'contrast_factor': 1.2},
    #     segment_params={'threshold_method': 'otsu', 'min_distance': 15},
    #     properties_params={'min_area': 50},
    #     save_path="grain_analysis_results.png",
    #     save_csv=True
    # )