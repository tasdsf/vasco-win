import cv2
import numpy as np
import mss

def nothing(x):
    pass

# Setup da janela de controlos
cv2.namedWindow("Trackbars")
cv2.createTrackbar("L-H", "Trackbars", 85, 179, nothing)
cv2.createTrackbar("L-S", "Trackbars", 100, 255, nothing)
cv2.createTrackbar("L-V", "Trackbars", 100, 255, nothing)
cv2.createTrackbar("U-H", "Trackbars", 105, 179, nothing)
cv2.createTrackbar("U-S", "Trackbars", 255, 255, nothing)
cv2.createTrackbar("U-V", "Trackbars", 255, 255, nothing)

monitor = {"top": 1200, "left": 905, "width": 100, "height": 110}

with mss.mss() as sct:
    while True:
        img = np.array(sct.grab(monitor))
        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Ler valores das Trackbars
        l_h = cv2.getTrackbarPos("L-H", "Trackbars")
        l_s = cv2.getTrackbarPos("L-S", "Trackbars")
        l_v = cv2.getTrackbarPos("L-V", "Trackbars")
        u_h = cv2.getTrackbarPos("U-H", "Trackbars")
        u_s = cv2.getTrackbarPos("U-S", "Trackbars")
        u_v = cv2.getTrackbarPos("U-V", "Trackbars")

        lower = np.array([l_h, l_s, l_v])
        upper = np.array([u_h, u_s, u_v])

        mask = cv2.inRange(hsv, lower, upper)
        res = cv2.bitwise_and(frame, frame, mask=mask)

        cv2.imshow("Frame", frame)
        cv2.imshow("Mask", mask)
        cv2.imshow("Res (O que o bot vê)", res)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print(f"Valores finais: lower = [{l_h}, {l_s}, {l_v}], upper = [{u_h}, {u_s}, {u_v}]")
            break

cv2.destroyAllWindows()