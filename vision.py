import ollama 


def get_image_description(image_path):
    response = ollama.chat(
        model='granite3.2-vision',
        messages=[{
            'role': 'user',
            'content': """
This image is from an Indian school science textbook (NCERT), 
for Class 9 or 10. It is either a diagram or a simple image.
Describe exactly what you see. Name all visible 
structures, organelles, labels, or components directly. 
Do not say 'without context' or 'it is difficult to determine'. 
Just describe what is visible in the image as if explaining 
it to a student.
""",
            'images': [image_path]
        }],
        options={
            'num_gpu': 999
        }
    ) 
    
    return response['message']['content']