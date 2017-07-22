from bgl import *
import math

def draw_circle(cx, cy, r, ls):
    # assert(ls>0)
    glBegin(GL_LINE_LOOP)
    glColor3f(0.0, 0.0, 0.0)
    for i in range(ls):
        theta = 2.0*3.1415926*i/ls
        x = r*math.cos(theta)
        y = r*math.sin(theta)
        glVertex2f(x+cx, y+cy)
    glEnd()

def draw_dot(cx, cy):
    glPointSize(10.0);
    glBegin(GL_POINTS)
    glColor3f(0.0, 1.0, 0.0)
    glVertex2f(cx, cy)
    glEnd()
