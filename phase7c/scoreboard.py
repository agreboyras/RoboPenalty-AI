"""Own 5x7 raster lettering assembled as horizontal visual strokes in world space."""
from phase7b.visual_scene import Primitive,box,connector

FONT={
'A':['01110','10001','10001','11111','10001','10001','10001'],
'B':['11110','10001','10001','11110','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'G':['01111','10000','10000','10111','10001','10001','01110'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'J':['00111','00010','00010','00010','10010','10010','01100'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'N':['10001','11001','11001','10101','10011','10011','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'P':['11110','10001','10001','11110','10000','10000','10000'],
'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'Y':['10001','10001','01010','00100','00100','00100','00100'],
'0':['01110','10001','10011','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','10001','00001','00010','00100','01000','11111'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'],
'5':['11111','10000','10000','11110','00001','00001','11110'],
'6':['01110','10000','10000','11110','10001','10001','01110'],
'7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'],
'9':['01110','10001','10001','01111','00001','00001','01110'],
'/':['00001','00010','00010','00100','01000','01000','10000'],
' ':['00000']*7,
}

def rectangles(bits):
    """Pack lit pixels into nonoverlapping rectangles instead of one row each."""
    pixels=[[value=='1' for value in row] for row in bits]
    result=[]
    for row in range(7):
        for col in range(5):
            if not pixels[row][col]:continue
            end=col
            while end<5 and pixels[row][end]:end+=1
            bottom=row+1
            while bottom<7 and all(pixels[bottom][c] for c in range(col,end)):bottom+=1
            for r in range(row,bottom):
                for c in range(col,end):pixels[r][c]=False
            result.append((row,col,bottom-row,end-col))
    return result

def lettering(text,top,scale,name,color=(.88,.97,1.,1)):
    width=(len(text)*6-1)*scale
    result=[]
    for index,char in enumerate(text):
        for row,col,height,length in rectangles(FONT[char]):
            y=width/2-(index*6+col+(length-1)/2)*scale
            z=top-(row+(height-1)/2)*scale
            result.append(Primitive(f'{name}_{index}_{row}_{col}','box',
                (11.70,y,z),(.012,length*scale*.48,height*scale*.48),color,emission=.75))
    return result

def screen_frame():
    return [box('screen_frame',(12.,0,5.),(.22,5.,1.45),(.16,.28,.35,1)),
            Primitive('screen_panel','box',(11.8,0,5.),(.08,4.8,1.25),(.008,.017,.028,1),emission=.2),
            box('screen_accent',(11.68,0,3.91),(.02,4.4,.025),(.04,.65,.72,1)),
            connector('screen_pole_left',(12.2,-3.,0),(12.2,-3.,4.),.09,(.2,.25,.3,1)),
            connector('screen_pole_right',(12.2,3.,0),(12.2,3.,4.),.09,(.2,.25,.3,1)),
            *lettering('ROBOPENALTY AI',5.95,.10,'screen_title')]

def floodlights():
    result=[]
    for side in (-1,1):
        y=side*8.
        result.append(connector(f'reflector_mast_{side}',(8,y,.5),(8,y,6.3),.055,(.25,.31,.36,1)))
        result.append(box(f'reflector_frame_{side}',(8,y,6.3),(.15,.65,.4),(.05,.075,.1,1)))
        for row in range(2):
            for col in range(3):
                result.append(Primitive(f'reflector_led_{side}_{row}_{col}','box',
                    (7.83,y+(col-1)*.39,6.3+(row-.5)*.35),(.025,.16,.13),
                    (1.,.95,.78,1),emission=1.))
    return result

def score_lines(status):
    goals=int(status.get('goals',0));saves=int(status.get('saves',0))
    penalty=int(status.get('penalty',0));total=int(status.get('total',5))
    return lettering(f'GOLES {goals} ATAJ {saves}',4.92,.075,'screen_score')+lettering(
        f'TIRO {penalty}/{total}',4.17,.045,'screen_penalty',(.45,.84,.91,1))
