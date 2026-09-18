"""Compact character rows for teams of one to four."""
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from .chevron import ChevronCardGenerator, COLORS
from ..services.enka import character_stats

class TeamRowGenerator(ChevronCardGenerator):
    def render(self, uid, profile, c, custom, splash, background, weapon_image,
               talents, talent_images, artifacts, artifact_images, const_images):
        canvas=Image.new('RGBA',(2400,600),'#171b20')
        accent=COLORS.get(c.element.name.capitalize(),'#bfc3c8')
        if background is not None:
            bg=ImageOps.fit(background.convert('RGBA'),canvas.size,method=Image.Resampling.LANCZOS)
            canvas=Image.blend(canvas,bg.filter(ImageFilter.GaussianBlur(3)),.32)
        panel_fill=(0,0,0,128)
        if splash is not None:
            art=splash.convert('RGBA')
            # Remove transparent padding, preserving the splash alpha.
            bounds=art.getchannel('A').point(lambda alpha: 255 if alpha > 32 else 0).getbbox()
            if bounds:
                art=art.crop(bounds)
                art=ImageOps.fit(art,(490,485),method=Image.Resampling.LANCZOS,centering=(.5,.5))
                canvas.alpha_composite(art,(65,16))
        draw=ImageDraw.Draw(canvas)
        draw.rounded_rectangle((8,8,2391,591),radius=24,outline=accent,width=3)
        for i,k in enumerate(c.constellations[:6]):
            self._medallion(canvas,(45,54+i*83),const_images[i] if i<len(const_images) else None,
                            f'C{i+1}',accent,k.unlocked,23,glow=k.unlocked,locked=not k.unlocked)
        for i,t in enumerate(talents):
            self._medallion(canvas,(579,75+i*115),talent_images[i],str(t.level),accent,True,29,glow=t.level>=10)
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(310,511),c.name,32,width=470,anchor='ma')
        self._text(draw,(310,556),f'Lv. {c.level}  |  UID {uid}',20,accent,anchor='ma')
        by_slot={a.equip_type.value:(a,img) for a,img in zip(artifacts,artifact_images)}
        slots=['EQUIP_BRACER','EQUIP_NECKLACE','EQUIP_SHOES','EQUIP_RING','EQUIP_DRESS']
        for i,slot in enumerate(slots):
            self._artifact(canvas,(650+i*346,25),by_slot.get(slot),accent,panel_fill)
        self._panel(canvas,(650,260,1210,565),fill=panel_fill)
        self._paste(canvas,weapon_image,(665,288,170,200))
        draw=ImageDraw.Draw(canvas)
        self._text(draw,(850,285),c.weapon.name,27,width=340)
        self._text(draw,(850,337),f'Lv. {c.weapon.level}  R{c.weapon.refinement}',24,accent)
        for i,s in enumerate(c.weapon.stats[:2]):
            from .chevron import percentage
            self._text(draw,(850,385+i*70),s.type.value.replace('FIGHT_PROP_','').replace('_',' '),14,width=330)
            self._text(draw,(850,409+i*70),f'{s.value:g}'+('%' if percentage(s) else ''),23,accent)
        self._panel(canvas,(1230,260,2378,565),fill=panel_fill)
        stats=character_stats(c)
        fields=[('HP','hp',False),('ATK','atk',False),('DEF','def',False),('EM','em',False),
                ('CRIT Rate','cr',True),('CRIT DMG','cd',True),('Energy Recharge','er',True),(stats['element']+' DMG','elem_bonus',True)]
        draw=ImageDraw.Draw(canvas)
        for i,(label,key,pct) in enumerate(fields):
            x=1260+(i//4)*555; y=287+(i%4)*65
            self._text(draw,(x,y),label,23,width=300)
            value=f'{stats[key]:.1f}%' if pct else f'{stats[key]:.0f}'
            self._text(draw,(x+490,y),value,27,accent,anchor='ra')
        return canvas


