## YOLOv3 in tesnorflow2.x-keras

### 测试效果

- COCO2017

<img src="https://raw.githubusercontent.com/yyccR/Pictures/master/yolov3/yolo_sample1.png" width="350" height="230"/>  <img src="https://raw.githubusercontent.com/yyccR/Pictures/master/yolov3/yolo_sample2.png" width="350" height="230"/>

<img src="https://raw.githubusercontent.com/yyccR/Pictures/master/yolov3/yolo_sample3.png" width="350" height="230"/>  <img src="https://raw.githubusercontent.com/yyccR/Pictures/master/yolov3/yolo_sample4.png" width="350" height="230"/>


### Requirements

`pip3 install -r requirements.txt`

### Get start

1. 训练
```python
python3 yolov3.py
```

2. tensorboard
```python
tensorboard --host 0.0.0.0 --logdir ./logs/ --port 8053 --samples_per_plugin=images=40
```    

3. 查看
```python
http://127.0.0.1:8053
```    


### 训练自己的数据

1. [labelme](https://github.com/wkentaro/labelme)打标自己的数据, 导出为coco格式

2. 参考`CoCoDataGenrator`类实现自己的generator
    
3. `python3 yolov3.py` 训练你的数据