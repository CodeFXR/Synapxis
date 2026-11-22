try:
    from textual_image.widget import Image
    HAS_IMAGE_LIB = True
except ImportError:
    Image = None
    HAS_IMAGE_LIB = False
