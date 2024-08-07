
def test_layout():
    import cv2

    from telos import Layout
   
    model = Layout(conf_thres=0.3, iou_thres=0.5)
    img = cv2.imread("tests/test_img/page_p6.png")

    # Detect Objects
    result = model(img)
    result_T = model._telos()
    # print(result_T)

    # Draw detections
    combined_img = model.draw_detections(img,mask_alpha=0.2)
    cv2.imwrite("output-layout.jpg", combined_img)