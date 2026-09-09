"""Angled character-card layout based on the user's sketch."""
import asyncio
from io import BytesIO
from math import cos, sin, pi

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageChops, ImageColor, ImageFilter

from .character_card import CharacterCardGenerator, namecard_urls, _PKG_ROOT
from ..services.enka import character_stats
from ..services.images import load_custom_image
from ..services.net import new_session

SIZE = (2000, 1200)
COLORS = {'Pyro': '#f16b49', 'Hydro': '#42b9ee', 'Electro': '#b68aef',
          'Cryo': '#83dce8', 'Anemo': '#52d5ad', 'Geo': '#efbd47',
          'Dendro': '#a4cf48', 'None': '#bfc3c8'}


def element_background(accent):
    """Local charcoal halftone with an element-tinted art panel."""
    rgb = ImageColor.getrgb(accent)
    canvas = Image.new('RGBA', SIZE)
    draw = ImageDraw.Draw(canvas)
    for y in range(SIZE[1]):
        v = int(30 - 13 * y / SIZE[1])
        draw.line((0, y, SIZE[0], y), fill=(v, v, v, 255))
    for y in range(0, SIZE[1], 14):
        for x in range((y // 14 % 2) * 7, SIZE[0], 14):
            draw.ellipse((x, y, x+3, y+3), fill=(8, 8, 8, 255))
    for x in range(-1200, 2200, 260):
        draw.polygon([(x,0),(x+65,0),(x+1265,1200),(x+1200,1200)], fill=(29,29,29,255))
    left=[(24,24),(470,24),(835,510),(370,1176),(24,1176)]
    draw.polygon(left, fill=tuple(int(v*.22) for v in rgb)+(255,))
    return canvas


def percentage(stat):
    name=stat.type.value
    return any(token in name for token in ('PERCENT','CRITICAL','EFFICIENCY','HURT','HEAL_ADD','HEALED_ADD'))


class ChevronCardGenerator(CharacterCardGenerator):
    @staticmethod
    def _panel(canvas, box, radius=16, polygon=False, fill=(16,18,16,178), outline=(160,170,160,150)):
        # Composite onto the background rather than storing alpha in the JPEG.
        layer=Image.new('RGBA',canvas.size)
        draw=ImageDraw.Draw(layer)
        if polygon:
            draw.polygon(box,fill=fill)
        else:
            draw.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=2)
        canvas.alpha_composite(layer)

    @staticmethod
    def _namecard_tint(background, accent):
        if background is None:
            rgb=ImageColor.getrgb(accent)
        else:
            sample=background.convert('RGB').resize((64,64)).quantize(colors=8)
            palette=sample.getpalette()
            # Prefer a prominent colourful swatch over white/grey decoration.
            candidates=[]
            for count,index in sample.getcolors():
                color=palette[index*3:index*3+3]
                saturation=(max(color)-min(color))/max(1,max(color))
                candidates.append((count*(.1+saturation),color))
            rgb=max(candidates,key=lambda item:item[0])[1]
        return tuple(round(channel*.32) for channel in rgb)+(178,)

    def _font(self, size):
        return ImageFont.truetype(self.font_path, size)

    def _text(self, draw, xy, text, size=24, fill='#f4f1ec', width=None, anchor='la'):
        text = str(text)
        font = self._font(size)
        if width:
            while size > 14 and draw.textlength(text, font=font) > width:
                size -= 1
                font = self._font(size)
            while text and draw.textlength(text, font=font) > width:
                text = text[:-2] + '…'
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)

    @staticmethod
    def _paste(canvas, image, box):
        if image is None:
            return
        x, y, w, h = box
        image = ImageOps.contain(image.convert('RGBA'), (w, h), Image.Resampling.LANCZOS)
        canvas.alpha_composite(image, (x + (w-image.width)//2, y + (h-image.height)//2))

    @staticmethod
    def _local(name):
        try:
            with Image.open(_PKG_ROOT / name) as image:
                return image.convert('RGBA')
        except OSError:
            return None

    def _stars(self, draw, x, y, count, radius=7):
        for i in range(int(count)):
            points=[]
            for k in range(10):
                angle=-pi/2 + k*pi/5
                r=radius if k%2==0 else radius*.43
                points.append((x+i*22+cos(angle)*r, y+sin(angle)*r))
            draw.polygon(points, fill='#e8c88d')

    async def generate_card(self, uid, char_id, *, profile=None, custom_image=None):
        profile = profile if profile is not None else await self.player_data_provider.fetch_player_profile(uid)
        c = next((c for c in profile.characters if str(c.id)==str(char_id)), None)
        if c is None:
            raise RuntimeError(f'Character {char_id} is unavailable for UID {uid}')
        if not c.name:
            raise RuntimeError('Character metadata is missing. Refresh the game assets.')
        custom = load_custom_image(custom_image) if custom_image is not None else await self._load_custom_splash(char_id)
        talents_by_id={t.id:t for t in c.talents}
        talents=[talents_by_id[i] for i in c.talent_order if i in talents_by_id][:3]
        slots=['EQUIP_BRACER','EQUIP_NECKLACE','EQUIP_SHOES','EQUIP_RING','EQUIP_DRESS']
        artifacts=sorted(c.artifacts, key=lambda a: slots.index(a.equip_type.value))[:5]
        async with new_session() as session:
            urls=[c.weapon.icon]+[t.icon for t in talents]+[a.icon for a in artifacts]+[k.icon for k in c.constellations[:6]]
            images=await asyncio.gather(*[self._load_image(session,u) for u in urls])
            splash=custom if custom is not None else await self._load_image(session,c.icon.gacha)
            background=None
            for url in namecard_urls(c):
                background=await self._load_image(session,url)
                if background is not None:
                    break
        n=len(talents); a=len(artifacts)
        weapon_image=images[0]
        talent_images=images[1:1+n]
        artifact_images=images[1+n:1+n+a]
        const_images=images[1+n+a:]
        canvas=self.render(uid,profile,c,custom,splash,background,weapon_image,
                           talents,talent_images,artifacts,artifact_images,const_images)
        buffer=BytesIO()
        canvas.convert('RGB').save(buffer,'JPEG',quality=95)
        buffer.seek(0)
        buffer.name=f'{char_id}.jpg'
        return buffer

    def render(self, uid, profile, c, custom, splash, background, weapon_image,
               talents, talent_images, artifacts, artifact_images, const_images):
        accent=COLORS.get(c.element.name.capitalize(),'#c1c9d4')
        panel_fill=self._namecard_tint(background,accent)
        canvas=element_background(accent)
        if background is not None:
            bg=ImageOps.fit(background.convert('RGBA'),SIZE,method=Image.Resampling.LANCZOS)
            bg=bg.filter(ImageFilter.GaussianBlur(radius=5))
            # Subdue the right-side namecard; the original left crop is
            # composited separately below and stays sharp and unchanged.
            canvas=Image.blend(Image.new('RGBA',SIZE,'#151915'),bg,.43)
        left=[(24,24),(470,24),(835,510),(370,1176),(24,1176)]
        if background is not None:
            # Clip the namecard to the character section only.
            bg=ImageOps.fit(background.convert('RGBA'),(840,1152),method=Image.Resampling.LANCZOS)
            layer=Image.new('RGBA',SIZE)
            layer.alpha_composite(bg,(24,24))
            mask=Image.new('L',SIZE)
            ImageDraw.Draw(mask).polygon(left,fill=255)
            layer.putalpha(ImageChops.multiply(layer.getchannel('A'),mask))
            canvas=Image.alpha_composite(canvas,layer)
        if splash is not None:
            # Official wide art is cropped at its centre; portrait custom art
            # uses the same cover fit, confined to the left polygon.
            art=ImageOps.fit(splash.convert('RGBA'),(840,1152),method=Image.Resampling.LANCZOS)
            layer=Image.new('RGBA',SIZE)
            layer.alpha_composite(art,(24,24))
            mask=Image.new('L',SIZE)
            ImageDraw.Draw(mask).polygon(left,fill=255)
            layer.putalpha(ImageChops.multiply(layer.getchannel('A'),mask))
            canvas=Image.alpha_composite(canvas,layer)
        draw=ImageDraw.Draw(canvas)
        # The two angled strips carry three talents and six constellations.
        ribbon=[(470,24),(600,24),(960,510),(500,1176),(370,1176),(835,510)]
        draw.polygon(ribbon,fill='#303030')
        draw.line([(470,24),(835,510),(370,1176)],fill=accent,width=3)
        draw.line([(600,24),(960,510),(500,1176)],fill=accent,width=2)
        for index,talent in enumerate(talents):
            x,y=[(666,189),(735,281),(804,373)][index]
            self._medallion(canvas,(x,y),talent_images[index],str(talent.level),accent,True,31)
        for index,constellation in enumerate(c.constellations[:6]):
            x=int(835-index*73); y=600+index*105
            icon=const_images[index] if index<len(const_images) else None
            self._medallion(canvas,(x,y),icon,f'C{index+1}',accent,constellation.unlocked,31)
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(54,53),'CHARACTER BUILD',18,accent)
        # Weapon and player are stacked beside the top-right stat panel.
        self._panel(canvas,(910,45,1404,284),fill=panel_fill)
        self._text(draw,(1072,66),'WEAPON',17,accent)
        self._paste(canvas,weapon_image,(922,78,140,157))
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(1072,102),c.weapon.name,27,width=306)
        cap=f'/{c.weapon.max_level}' if c.weapon.max_level else ''
        self._text(draw,(1072,151),f'Lv. {c.weapon.level}{cap}  •  R{c.weapon.refinement}',21)
        self._stars(draw,1080,195,c.weapon.rarity)
        for i,stat in enumerate(c.weapon.stats[:2]):
            value=f'{stat.value:g}'+('%' if percentage(stat) else '')
            label={'FIGHT_PROP_BASE_ATTACK':'BASE ATK','FIGHT_PROP_ELEMENT_MASTERY':'ELEMENTAL MASTERY',
                   'FIGHT_PROP_CRITICAL':'CRIT RATE','FIGHT_PROP_CRITICAL_HURT':'CRIT DMG',
                   'FIGHT_PROP_CHARGE_EFFICIENCY':'ENERGY RECHARGE','FIGHT_PROP_ATTACK_PERCENT':'ATK',
                   'FIGHT_PROP_HP_PERCENT':'HP','FIGHT_PROP_DEFENSE_PERCENT':'DEF'}.get(stat.type.value,'STAT')
            self._text(draw,(935+i*230,219),label,14,'#bdbdbd',width=215)
            self._text(draw,(935+i*230,245),value,23,accent)
        self._panel(canvas,(1000,305,1404,491),fill=panel_fill)
        self._text(draw,(1026,327),'PLAYER',17,accent)
        self._text(draw,(1026,365),profile.player.nickname or 'Traveler',28,width=345)
        self._text(draw,(1026,407),f'UID  {uid}',21,'#bdbdbd')
        self._text(draw,(1026,449),f'Friendship  {c.friendship_level}',19,'#bdbdbd')
        self._panel(canvas,(1430,45,1976,491),fill=panel_fill)
        self._text(draw,(1458,67),'CHARACTER STATS',17,accent)
        stats=character_stats(c)
        fields=[('Max HP','hp','hp','{:.0f}'),('ATK','atk','atk','{:.0f}'),
                ('DEF','def','def','{:.0f}'),('Elemental Mastery','em','em','{:.0f}'),
                ('CRIT Rate','cr','cr','{:.1f}%'),('CRIT DMG','cd','cd','{:.1f}%'),
                ('Energy Recharge','er','er','{:.1f}%'),
                (f'{stats["element"]} DMG','elem_bonus',stats['element'].lower(),'{:.1f}%')]
        for i,(label,key,icon,fmt) in enumerate(fields):
            y=111+i*45
            if i%2==0: self._panel(canvas,(1446,y-4,1960,y+35),radius=6,fill=(160,170,160,30),outline=None)
            self._paste(canvas,self._local(f'assets/icons/{icon}.png'),(1456,y,28,28))
            draw=ImageDraw.Draw(canvas)
            self._text(draw,(1499,y+2),label,20,width=290)
            self._text(draw,(1937,y+2),fmt.format(stats[key]),23,anchor='ra')
        # Character identity spans the centre of the right-hand side.
        self._panel(canvas,[(969,518),(1976,518),(1976,654),(875,654)],polygon=True,fill=panel_fill)
        draw.line((969,518,1976,518),fill=accent,width=3)
        self._text(draw,(984,547),c.name,46,width=540)
        cap=f'/{c.max_level}' if c.max_level else ''
        self._text(draw,(1815,547),f'Lv. {c.level}{cap}',46,width=285,anchor='ra')
        self._stars(draw,992,616,c.rarity,8)
        self._paste(canvas,self._local(f'assets/icons/{stats["element"].lower()}.png'),(1861,552,60,60))
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(900,679),'ARTIFACTS',17,accent)
        # Five artifacts in the sketch's 3-by-2 grid; branding occupies cell 6.
        by_slot={a.equip_type.value:(a,img) for a,img in zip(artifacts,artifact_images)}
        slots=['EQUIP_BRACER','EQUIP_NECKLACE','EQUIP_SHOES','EQUIP_RING','EQUIP_DRESS']
        for i,slot in enumerate(slots):
            x=900+(i%3)*360; y=711+(i//3)*231
            self._artifact(canvas,(x,y),by_slot.get(slot),accent,panel_fill)
        self._paste(canvas,self._local('assets/logo.png'),(1734,968,150,150))
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(1809,1125),'RECARD',17,accent,anchor='ma')
        draw.rectangle((12,12,1987,1187),outline='#555555',width=2)
        return canvas

    def _medallion(self,canvas,xy,icon,label,accent,unlocked,radius):
        x,y=xy; draw=ImageDraw.Draw(canvas)
        draw.ellipse((x-radius-4,y-radius-4,x+radius+4,y+radius+4),fill='#101010',outline=accent if unlocked else '#526171',width=2)
        if icon is not None and not unlocked:
            icon=ImageEnhance.Brightness(ImageOps.grayscale(icon).convert('RGBA')).enhance(.4)
        self._paste(canvas,icon,(x-radius+8,y-radius+8,2*radius-16,2*radius-16))
        draw=ImageDraw.Draw(canvas)
        draw.rounded_rectangle((x-26,y+radius-6,x+26,y+radius+23),radius=9,fill='#090909')
        self._text(draw,(x,y+radius-3),label,18,accent if unlocked else '#8994a3',anchor='ma')

    def _artifact(self,canvas,xy,item,accent,panel_fill=(16,18,16,178)):
        x,y=xy; draw=ImageDraw.Draw(canvas)
        self._panel(canvas,(x,y,x+342,y+212),radius=13,fill=panel_fill)
        if item is None:
            self._text(draw,(x+171,y+91),'Not equipped',20,'#718094',anchor='ma')
            return
        a,image=item
        self._paste(canvas,image,(x+4,y+10,112,116))
        draw=ImageDraw.Draw(canvas)
        cv=sum(stat.value * (2 if stat.type.value == 'FIGHT_PROP_CRITICAL' else 1)
               for stat in a.sub_stats
               if stat.type.value in ('FIGHT_PROP_CRITICAL','FIGHT_PROP_CRITICAL_HURT'))
        self._stars(draw,x+16,y+145,a.rarity,6)
        self._text(draw,(x+14,y+174),f'+{a.level}',22,accent)
        main=a.main_stat
        prop=main.type.value.replace('FIGHT_PROP_','').replace('_',' ').title()
        aliases={'Critical':'CRIT Rate','Critical Hurt':'CRIT DMG','Charge Efficiency':'Energy Recharge',
                 'Attack Percent':'ATK','Hp Percent':'HP','Defense Percent':'DEF',
                 'Fire Add Hurt':'Pyro DMG','Water Add Hurt':'Hydro DMG','Elec Add Hurt':'Electro DMG',
                 'Wind Add Hurt':'Anemo DMG','Ice Add Hurt':'Cryo DMG','Rock Add Hurt':'Geo DMG','Grass Add Hurt':'Dendro DMG'}
        self._text(draw,(x+126,y+15),aliases.get(prop,prop),17,'#bdbdbd',width=199)
        self._text(draw,(x+126,y+43),f'{main.value:g}'+('%' if percentage(main) else ''),29,accent,width=105)
        self._text(draw,(x+324,y+50),f'{cv:.1f} CV',18,accent,width=88,anchor='ra')
        short={'FIGHT_PROP_CRITICAL':'CR','FIGHT_PROP_CRITICAL_HURT':'CD','FIGHT_PROP_CHARGE_EFFICIENCY':'ER',
               'FIGHT_PROP_ELEMENT_MASTERY':'EM','FIGHT_PROP_ATTACK':'ATK','FIGHT_PROP_HP':'HP','FIGHT_PROP_DEFENSE':'DEF',
               'FIGHT_PROP_ATTACK_PERCENT':'ATK','FIGHT_PROP_HP_PERCENT':'HP','FIGHT_PROP_DEFENSE_PERCENT':'DEF'}
        for i,stat in enumerate(a.sub_stats[:4]):
            y0=y+91+i*27
            self._text(draw,(x+126,y0),short.get(stat.type.value,stat.type.name),17,'#bdbdbd',width=100)
            self._text(draw,(x+324,y0),f'{stat.value:g}'+('%' if percentage(stat) else ''),19,anchor='ra')

