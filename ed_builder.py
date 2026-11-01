def calc_image(vol, out):
    """Generate a calculation record using available fonts."""
    im = Image.new('RGB', (1200, 520), 'white')
    d = ImageDraw.Draw(im)

    def load_font(size):
        for name in (
            'C:/Windows/Fonts/arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)

    title_font = load_font(32)
    body_font = load_font(25)
    total_font = load_font(42)
    footer_font = load_font(17)

    d.rectangle((2, 2, 1197, 516), outline='#999999', width=3)
    d.rectangle((3, 3, 1196, 80), fill='#ac3129')
    d.text((30, 24), 'Cubic Yards Calculation',
           font=title_font, fill='white')

    dimensions = (
        f"Length: {vol['length']:g} ft     "
        f"Width: {vol['width']:g} ft     "
        f"Height: {vol['height']:g} ft"
    )
    d.text((28, 115), dimensions, font=body_font, fill='#222')
    d.text((28, 174),
           f"Container capacity: {vol['container']:.2f} CYD",
           font=body_font, fill='#222')

    if vol['overage']:
        d.text((28, 225),
               f"Documented overage: {vol['overage']:.2f} CYD",
               font=body_font, fill='#222')
        d.text((28, 283),
               'Uniform overage height requires measurement support.',
               font=body_font, fill='#a12e22')

    d.line((25, 358, 1170, 358), fill='#ddd', width=3)
    d.text((28, 380),
           f"Calculated measured volume: {vol['total']:.2f} CYD",
           font=total_font, fill='#222')
    d.text((28, 485),
           'Generated calculation record - NOT a CalculatorSoup screenshot',
           font=footer_font, fill='#555')
    im.save(out)
