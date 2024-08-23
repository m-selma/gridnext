import torch
import random
import numpy as np
import torchvision.transforms.functional as TF

class HSV_light:
    """Apply a light HSV transformation plus other color transforms. Inspired by the description in 
        'Quantifying the effects of data augmentation and stain color normalization in convolutional 
        neural networks for computational pathology' 10.1016/j.media.2019.101544
    """

    def __init__(self, 
                 adjust_hue=0.5, 
                 adjust_brightness=0.5, 
                 adjust_contrast=0.5, 
                 adjust_gamma=0.5,                 
                 adjust_saturation=0.5, 
                 adjust_sharpness=0.5,
                 range_distribution="uniform"):
        """
        Args:
         adjust_{brightness, contrast, gamma, hue, saturation, sharpness}:
            probability that the torchvision.transforms.functional.x will be applied
         range_distribution: {"normal"|"uniform"} . If a modification is applied, a value must be chosen from within a range,
            if range is uniform all the range will be covered equally, if range is normal the mean of 
            the range will be more commonly used.
         """
        
        self.adjust_hue=adjust_hue
        self.adjust_contrast=adjust_contrast
        self.adjust_brightness=adjust_brightness
        self.adjust_gamma=adjust_gamma
        self.adjust_saturation=adjust_saturation
        self.adjust_sharpness=adjust_sharpness
        self.range_distribution=range_distribution
        self.hue_range=(-0.16,0.16)
        self.contrast_range=(0.7,1.3)
        self.brightness_range=(0.7,1.3)        
        self.gamma_range=(0.5,1.5)        
        self.saturation_range=(0.5,1.2)
        self.sharpness_range=(0,2)
        self.mu=0.5
        self.sigma=0.166666

    def adjust(self,x,func):
        """
        Args:
         x: tensor image
         func: which function to apply
         """
        if self.range_distribution=="normal":
            #it's necessary to clip since I am mapping the range and I am still interested in
            # getting the lowest and highest value of the range, just with a small probability
            r=np.random.normal(self.mu,self.sigma)
            r=np.clip(r,0.0,1.0)
        elif self.range_distribution=="uniform":
            r=np.random.random()

        arange=getattr(self,func+"_range")
        value=(arange[1]-arange[0])*r+arange[0]

        afunction=getattr(TF,"adjust_"+func)
        return afunction(x,value)
        

    def __call__(self, x):
        for t in ["hue","brightness","contrast","gamma","saturation","sharpness"]:
            prob_t=getattr(self,"adjust_"+t)
            if torch.rand(1).item() < prob_t:
                x=self.adjust(x, t)
        return x

class RandomRot90:
    def __init__(self, p):
        self.p = p
        self.angles = [90, 180, 270]

    def __call__(self, x):
        if torch.rand(1).item() < self.p:
            angle = random.choice(self.angles)
            return TF.rotate(x, angle)
        return x