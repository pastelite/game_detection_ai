from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile
from io import BytesIO
from PIL import Image
import numpy as np
import torch
from torchvision.models import efficientnet_b4
from torchvision.transforms import functional as F
from model.efficient_net_modified import EfficientNetModified, load_efficientnetmodified
from model.my_simple_model import MySimpleModel, load_mysimplemodel
from model.my_simple_model2 import MySimpleModel2, load_mysimplemodel2
from dataset import label
import gradio as gr

models = {}
models_keys = ["efficientnet", "mysimplemodel", "mysimplemodel2"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    models["efficientnet"] = load_efficientnetmodified("checkpoints/new-eff/new-eff_11.pth")
    models["efficientnet"].eval()
    models["mysimplemodel"] = load_mysimplemodel("checkpoints/my-simple/my-simple_1.pth")
    models["mysimplemodel"].eval()
    models["mysimplemodel2"] = load_mysimplemodel2("checkpoints/my-shitty-model/my-shitty-model_7.pth")
    models["mysimplemodel2"].eval()
    yield models
    models.clear()

app = FastAPI(lifespan=lifespan)

@app.post("/images/")
async def create_upload_file(file: UploadFile = File(...)):

    contents = await file.read()  # <-- Important!

    # Convert from bytes to PIL image
    img = Image.open(BytesIO(contents)).convert("RGB")
    
    # transform image
    img_tensor: torch.Tensor = EfficientNetModified.transform(img) # type: ignore
    
    # predict
    model = models["efficientnet"]
    model.eval()
    with torch.no_grad():
        preds = model(img_tensor.unsqueeze(0))
        topk_index = torch.topk(preds, 5, 1).indices.squeeze(0)
        # print(topk_index)
        # probas = preds.softmax(1)
        # preds = probas.argmax(1)
        
    pred_summary = {}
    for idx in topk_index:
        class_id = idx.item()
        score = preds[0][class_id].item()
        class_name = label.GameLabel(class_id).name
        pred_summary[class_name] = score
        
    return {"filename": file.filename, "prediction": pred_summary}

def predict(image, topk, model_name):

    model = models[model_name]
    img = Image.fromarray(np.uint8(image)).convert('HSV')
    
    img_tensor: torch.Tensor = EfficientNetModified.transform(img)  # type: ignore
    model.eval()
    with torch.no_grad():
        preds = model(img_tensor.unsqueeze(0))
        topk_index = torch.topk(preds, topk, 1).indices.squeeze(0)
        # print(topk_index)
        
    pred_summary = []
    for idx in topk_index:
        class_id = idx.item()
        score = preds[0][class_id].item()
        class_name = label.GameLabel(class_id).name
        pred_summary.append([class_name,score])
        
    return pred_summary[0][0], pred_summary

gradio_app = gr.Interface(
    fn=predict,
    inputs=[gr.Image(), gr.Slider(minimum=1,maximum=30,value=5,step=1), gr.Dropdown(list(models_keys),value=models_keys[0])],
    outputs=[gr.Textbox(label="Predicted class", lines=3), gr.Dataframe(headers=["classes","score"])],
    allow_flagging="never"
)

gr.mount_gradio_app(app, gradio_app, "/gradio")