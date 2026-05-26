#!/usr/bin/env python3
# Render a high-fidelity 400x300 mockup of the RLCD dashboard (English-only).
import json, urllib.request, math, io, cairosvg
from PIL import Image, ImageDraw, ImageFont

S = 3
W, H = 400, 300
LAT, LON = 22.5431, 114.0579  # Shenzhen

LIB  = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
LIBR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
def f(p, s): return ImageFont.truetype(p, s*S)
time_f, big_f, temp_f = f(LIB,36), f(LIB,33), f(LIB,21)
title_f, pct_f        = f(LIB,15), f(LIB,13)
num_f, numb_f         = f(LIBR,13), f(LIB,13)
small_f, tiny_f       = f(LIBR,12), f(LIBR,11)

INK=(24,24,24); GRAY=(110,110,110); LINE=(165,165,165)
FAINT=(210,210,210); TRACK=(208,211,205); BG=(236,238,233)

cond, temp, icon = "Cloudy", "28", "partly"
try:
    u=(f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
       "&current=temperature_2m,weather_code&timezone=Asia/Shanghai")
    d=json.load(urllib.request.urlopen(u,timeout=10))
    temp=str(round(d["current"]["temperature_2m"]))
    wc=d["current"]["weather_code"]
    m={0:("Clear","clear"),1:("Clear","clear"),2:("Partly","partly"),3:("Cloudy","cloud"),
       45:("Fog","cloud"),48:("Fog","cloud"),51:("Drizzle","rain"),53:("Drizzle","rain"),
       55:("Rain","rain"),61:("Rain","rain"),63:("Rain","rain"),65:("Heavy","rain"),
       80:("Showers","rain"),81:("Showers","rain"),82:("Storm","rain"),95:("Storm","rain"),
       71:("Snow","snow"),73:("Snow","snow"),75:("Snow","snow")}
    cond,icon=m.get(wc,("Cloudy","partly"))
except Exception as e:
    print("weather fetch failed:",e)

img=Image.new("RGB",(W*S,H*S),BG); dr=ImageDraw.Draw(img)
def Xc(v): return v*S
def rrect(x0,y0,x1,y1,r,fill=None,outline=None,width=1):
    dr.rounded_rectangle([Xc(x0),Xc(y0),Xc(x1),Xc(y1)],radius=r*S,fill=fill,outline=outline,width=width*S)
def line(x0,y0,x1,y1,fill,width=1):
    dr.line([Xc(x0),Xc(y0),Xc(x1),Xc(y1)],fill=fill,width=width*S)
def text(x,y,s,font,fill=INK,anchor="la"):
    dr.text((Xc(x),Xc(y)),s,font=font,fill=fill,anchor=anchor)

def claude_robot(cx,cy,s):
    # Claude Code style friendly bot: rounded head, antenna, two eyes
    line(cx,cy-s*0.7,cx,cy-s*1.35,INK,2)
    dr.ellipse([Xc(cx-s*0.16-1),Xc(cy-s*1.5),Xc(cx+s*0.16+1),Xc(cy-s*1.2)],fill=INK)
    rrect(cx-s,cy-s*0.65,cx+s,cy+s*0.9,4,fill=INK)
    # ears
    rrect(cx-s-2.5,cy-s*0.1,cx-s,cy+s*0.4,2,fill=INK)
    rrect(cx+s,cy-s*0.1,cx+s+2.5,cy+s*0.4,2,fill=INK)
    # eyes (white rounded)
    for ex in (cx-s*0.42, cx+s*0.42):
        dr.ellipse([Xc(ex-2.4),Xc(cy-s*0.05-2.4),Xc(ex+2.4),Xc(cy-s*0.05+2.4)],fill=BG)

def whale(cx,cy,s):
    # left-facing stylized whale, filled
    dr.ellipse([Xc(cx-s),Xc(cy-s*0.62),Xc(cx+s*0.55),Xc(cy+s*0.62)],fill=INK)
    tail=[(cx+s*0.35,cy),(cx+s*1.05,cy-s*0.6),(cx+s*0.8,cy),(cx+s*1.05,cy+s*0.6)]
    dr.polygon([(Xc(p[0]),Xc(p[1])) for p in tail],fill=INK)
    # eye (white)
    dr.ellipse([Xc(cx-s*0.55),Xc(cy-s*0.22),Xc(cx-s*0.32),Xc(cy+s*0.01)],fill=BG)
    # spout
    line(cx-s*0.55,cy-s*0.7,cx-s*0.7,cy-s*1.15,INK,2)

def weather_icon(cx,cy,kind):
    su=11
    if kind in ("clear","partly"):
        sx,sy=(cx-6,cy-5) if kind=="partly" else (cx,cy-1)
        dr.ellipse([Xc(sx-su),Xc(sy-su),Xc(sx+su),Xc(sy+su)],outline=INK,width=2*S,fill=BG)
        if kind=="clear":
            for a in range(0,360,45):
                dx,dy=math.cos(math.radians(a)),math.sin(math.radians(a))
                line(sx+dx*(su+3),sy+dy*(su+3),sx+dx*(su+8),sy+dy*(su+8),INK,2)
    if kind in ("partly","cloud","rain","snow"):
        ox,oy=(cx+5,cy+5) if kind=="partly" else (cx,cy)
        dr.ellipse([Xc(ox-15),Xc(oy-3),Xc(ox+1),Xc(oy+13)],outline=INK,width=2*S,fill=BG)
        dr.ellipse([Xc(ox-5),Xc(oy-10),Xc(ox+13),Xc(oy+8)],outline=INK,width=2*S,fill=BG)
        dr.ellipse([Xc(ox+5),Xc(oy-2),Xc(ox+19),Xc(oy+12)],outline=INK,width=2*S,fill=BG)
        rrect(ox-15,oy+6,ox+19,oy+13,4,fill=BG,outline=INK,width=2)
        dr.rectangle([Xc(ox-13),Xc(oy+7),Xc(ox+17),Xc(oy+12)],fill=BG)
        if kind=="rain":
            for i in range(3):
                rx=ox-8+i*8; line(rx,oy+15,rx-3,oy+22,INK,2)

# HEADER
text(16,8,"14:30",time_f)
text(16,50,"IN  24.3°C   56%RH",small_f,GRAY)
weather_icon(298,24,icon)
text(338,13,f"{temp}°C",temp_f)
text(384,48,f"SHENZHEN · {cond}",small_f,GRAY,anchor="ra")
line(16,66,384,66,LINE,1)

# COLUMNS
line(205,74,205,286,FAINT,1)

# LEFT CLAUDE
def place_svg(path,cx,cy,size):
    px=int(size*S)
    png=cairosvg.svg2png(url=path,output_width=px,output_height=px)
    ic=Image.open(io.BytesIO(png)).convert("RGBA")
    blk=Image.new("RGBA",ic.size,(24,24,24,255))
    img.paste(blk,(int(Xc(cx)-px/2),int(Xc(cy)-px/2)),ic.split()[3])

place_svg("/tmp/lh_claudecode.svg",27,87,21)
text(46,76,"CLAUDE",title_f)
def bar(y,label,pct):
    text(16,y-1,label,num_f,GRAY)
    bx0,bx1=42,150
    rrect(bx0,y,bx1,y+11,5,fill=TRACK,outline=LINE,width=1)
    if pct>0.02: rrect(bx0,y,bx0+(bx1-bx0)*pct,y+11,5,fill=INK)
    text(158,y-2,f"{int(pct*100)}%",pct_f,INK)
bar(100,"5h",0.24); bar(122,"7d",0.56)
text(16,142,"reset in 1h 39m",tiny_f,GRAY)
line(16,162,196,162,FAINT,1)
yy=172
for lab,tok,cost in [("today","135M","$98.42"),("month","8.0B","$4.6k"),("total","9.5B","$5.6k")]:
    text(16,yy,lab,small_f,INK); text(82,yy,tok,num_f,INK); text(196,yy,cost,numb_f,INK,anchor="ra"); yy+=24

# RIGHT DEEPSEEK
place_svg("/tmp/lh_deepseek.svg",226,86,21)
text(247,76,"DEEPSEEK",title_f)
text(216,104,"balance (CNY)",small_f,GRAY)
text(300,116,"¥70.79",big_f,INK,anchor="ma")
line(216,162,384,162,FAINT,1)
yy=172
for lab,val in [("granted","¥0.00"),("topped","¥70.79"),("today","2.4M tok")]:
    text(216,yy,lab,small_f,INK); text(384,yy,val,numb_f,INK,anchor="ra"); yy+=24

screen=img.resize((W*2,H*2),Image.LANCZOS)
PAD=26
bez=Image.new("RGB",(W*2+PAD*2,H*2+PAD*2),(20,20,22)); d2=ImageDraw.Draw(bez)
d2.rounded_rectangle([6,6,bez.width-6,bez.height-6],radius=30,outline=(60,60,64),width=3)
bez.paste(screen,(PAD,PAD)); bez.save("/tmp/rlcd_mockup.png")
print("saved",bez.size,"weather:",temp,cond,icon)
