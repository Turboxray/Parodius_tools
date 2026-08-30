
Info
----

  PC-Engine Parodius Da! color hack v 1.0.

   This hack improves the colors and detail by modifying the unused colors in the palette data.
  Not tile data was altered, just palette entries. The game contained lots of duplicate color entries
  that was hiding existing pixel detail. This patch simply uses existing color cues to expand those
  duplicate entries into real colors/detail. This is quite a rare situation for a game to have detail
  that you couldn't see because they duplicated colors to hide it. I've never seen anything like this
  to this extent. So, this hack restores that detail.


   The hack also increases the vertical size of the game, removing the vertical auto-scroll, and showing
  the full vertical height of the level. This expands the viewable area from 224p to 240p. You'll need to
  adjust your CRT TV or scaler to view the full frame. Most emulators need to be adjusted as well - they
  don't typically show all 240 lines of PCE games.

   Per version 1.0, I have added some choices for some middle ground options for frame height. There are
  "208" and "216" options that show more of the vertical frame, with a slight bit of vertical scrolling
  (like the original). If you're running on a CRT TV and can't adjust for the full frame height, then
  this will be the next best options. The score and lives might get cut-off, depending on your setup, but
  the HUD is the most important visible part.

   I've included stock frame height as well, but it is not recommended as you can't fully appreciate the
  new color updates in some levels.. like the graveyard level or the first level with the animated water
  line at the bottom of the screen. The issue with the stock frame height, is that it requires you to move
  your ship all the way to the bottom of the screen to see that extra detail - which isn't likely in this
  game.. and impossible with the land collision on the first level.

  Note:

     The color choices I made for this hack are based on "composite" or "VCE" colors. This does not tailor
    the added colors for "RGB". The original game didn't seem to target RGB, so I did not as well.
    This means if you play it with "RGB" colors, they'll look over saturated (and slightly different).


Patch options
-------------

  Four versions of the patch are included. All of them contain the color hack;
  they differ in how much of the game's vertical area is shown (the original
  shows ~197 lines of the game above the HUD; the full hack shows all 224):

    Parodius_patch_vX_XX_stock_height  - colors ONLY. The HUD, window and scrolling are
                                         exactly as the original game.
    Parodius_patch_vX_XX_208h    - colors + 208 lines of game (mild auto-scroll).
    Parodius_patch_vX_XX_216h    - colors + 216 lines of game (slight auto-scroll).
    Parodius_patch_vX_XX_224h    - full hack: colors + 224 lines of the game (no vertical scrolling)

  Pick ONE and apply it to a clean rom.


History
-------

  v1.0  - Added patch options for the frame height: stock_height (colors only),
          208h, 216h, alongside the full 224h/240p hack.

  v0.99 - Initial release


How to
------

  Two patch formats are available: ips and xdelta.

   The patches require a headerless rom file. The headerless rom is 1,048,576 bytes in size.
  If you have a headered rom, you'll need to delete/remove the first 512 bytes from the file.



- 2026 TurboXray