#!/usr/bin/perl
# Generate palette.inc : readable, editable colour-block defs for Parodius.
# Source of truth = a v4 ROM + the Lua capture log (block locations).
# Each block is decoded from the ROM's packed 9-bit format into pal8/rgb() defs;
# re-assembling with PCEAS reproduces the exact ROM bytes (codec is lossless).
use strict; use warnings;

# usage: gen_palette_inc.pl [rom] [out]   (defaults: v4 rom -> palette.inc)
#   e.g. gen_palette_inc.pl "Parodius_Da__original.pce" palette_org.inc
my $ROM = $ARGV[0] // "Parodius Da! - Shinwa kara Owarai he (J)_v4.pce";
my $OUT = $ARGV[1] // "palette.inc";
my $LOG = "parodius_pal_blocks.txt";

my $d; { local $/; open my $F,"<:raw",$ROM or die "$ROM: $!"; $d=<$F>; close $F; }

# block set: abs => { count=>, cta=>{...} }
my %blk;
# primary (stage-tagged) log: blocks, CTAs, and which stage(s) loaded each block
open my $L,"<",$LOG or die "$LOG: $!";
while(<$L>){
  next unless /CTA=\$(\w+) block=\$\w+ block_abs=\$(\w+) count=\$(\w+)/;
  my ($cta,$abs,$c)=(hex($1),hex($2),hex($3));
  $blk{$abs}{count}=$c;
  $blk{$abs}{cta}{$cta}=1;
  $blk{$abs}{stage}{hex($1)}=1 if /stage=\$(\w+)/;
}
close $L;
# older capture(s) merged in for block coverage only (no stage info)
if (open my $L2,"<","$LOG.old"){
  while(<$L2>){
    next unless /CTA=\$(\w+) block=\$\w+ block_abs=\$(\w+) count=\$(\w+)/;
    my ($cta,$abs,$c)=(hex($1),hex($2),hex($3));
    $blk{$abs}{count}//=$c;
    $blk{$abs}{cta}{$cta}=1;
  }
  close $L2;
}
sub bsz { 1 + ($_[0]+1)*9 }
sub le16 { ord(substr($d,$_[0],1)) | (ord(substr($d,$_[0]+1,1))<<8) }

# Static parse of the palette POINTER TABLE = authoritative, complete block set
# (includes never-triggered blocks like the score-gated Special bosses).
# Table = groups of 4-byte entries [CTA_lo][CTA_hi][blk_lo][blk_hi], each group
# terminated by FF 00 00. Banks $38-$3B map to a fixed $4000-$BFFF window, so
# block abs = ptr + $6C000.
sub parse_table {
  my ($p,$end)=@_;
  while($p<$end){
    if(ord(substr($d,$p,1))==0xFF){ $p+=3; next; }   # group terminator FF 00 00
    my $cta=le16($p); my $b=le16($p+2);
    last unless $cta<=0x1FF && $b>=0x4000 && $b<=0xBFFF;
    my $abs=$b+0x6C000;
    $blk{$abs}{count}//=ord(substr($d,$abs,1));
    $blk{$abs}{cta}{$cta}=1;
    $p+=4;
  }
}
parse_table(0x70166,0x70200);   # intro / title / ending palette table ($4166)
parse_table(0x70630,0x71000);   # main level + Special palette table ($4630)

# clean original, to detect exactly which bytes v4 edited
my $oa; { local $/; open my $OO,"<:raw","Parodius_Da__original.pce" or die "$!"; $oa=<$OO>; close $OO; }

# find the pointer-table entry whose colour block covers a given ROM offset
sub find_block_for {
  my $off=shift;
  for(my $p=0x70000;$p<0x71FFC;$p++){
    my $cta=le16($p); my $b16=le16($p+2);
    next unless $cta<=0x1FF && $b16>=0x4000 && $b16<=0xBFFF;
    my $abs=$b16+0x6C000;
    next if $abs+1>=length($d);
    my $cnt=ord(substr($d,$abs,1));
    next if $cnt>0x3F;
    return ($abs,$cnt,$cta) if $abs<=$off && $off<$abs+bsz($cnt);
  }
  return ();
}

# auto-add any edited block the capture log missed, so every v4 edit is covered
my %cov; for my $a (keys %blk){ $cov{$_}=1 for ($a .. $a+bsz($blk{$a}{count})-1) }
my $added=0;
for my $i (0x70000..0x77FFF){
  next if substr($oa,$i,1) eq substr($d,$i,1);
  next if $cov{$i};
  my ($abs,$cnt,$cta)=find_block_for($i);
  if(defined $abs){
    $blk{$abs}{count}=$cnt; $blk{$abs}{cta}{$cta}=1; $added++;
    $cov{$_}=1 for ($abs .. $abs+bsz($cnt)-1);
  } else { warn sprintf("WARN: no block found for edit at \$%05X\n",$i); }
}
printf STDERR "auto-added %d edit-covering block(s) beyond the capture log\n",$added;

my @abs = sort {$a<=>$b} keys %blk;

# overlap report
my @ovl;
for my $i (0..$#abs-1){
  my $e=$abs[$i]+bsz($blk{$abs[$i]}{count});
  push @ovl, [$abs[$i],$e,$abs[$i+1]] if $e>$abs[$i+1];
}

open my $O,">",$OUT or die;
print $O "; ================================================================\n";
print $O "; palette.inc - Parodius colour blocks (data only), editable\n";
print $O ";   ", scalar(@abs)," blocks, decoded from the packed 9-bit ROM format.\n";
print $O ";   Edit the rgb(r,g,b) values (each component 0..7). The #RRGGBB\n";
print $O ";   comment above each 16-colour group is a VS Code preview swatch\n";
print $O ";   strip (regenerate to refresh after edits). The .db before each\n";
print $O ";   block is its group count.\n";
print $O ";   Block header = where the palette loads: BG or sprite section +\n";
print $O ";   subpalette index (decimal 0-15), then size (1 subpalette = 16 colours).\n";
print $O ";   'used:' = level(s)/mode that loaded it (L1 also covers title/menu/\n";
print $O ";   intro/ending; Special-1 = \$0A select + 1st half, Special-2 = \$0B\n";
print $O ";   score-gated 2nd half; ? = not seen in the tagged run).\n";
print $O ";   Requires palette_macros.inc (rgb()/pal8) - include it first.\n";
print $O "; ================================================================\n\n";

my $rtfail=0;
for my $ba (@abs){
  my $c=$blk{$ba}{count};
  my $bank=$ba>>13; my $org=0x4000+($ba & 0x1FFF);
  my @ctas = sort {$a<=>$b} keys %{$blk{$ba}{cta}};
  my %bysec;                              # VCE 0-255 = BG, 256-511 = sprite
  for my $cta (@ctas){
    my $sec = ($cta>=0x100) ? "sprite" : "BG";
    push @{$bysec{$sec}}, ($cta & 0xFF) >> 4;   # subpalette index (decimal), 0-15
  }
  my @loc;
  for my $sec ("BG","sprite"){ push @loc, "$sec palette ".join(",",@{$bysec{$sec}}) if $bysec{$sec}; }
  my $colours = ($c+1)*8;
  my $sp = $colours/16;
  my $sptxt = ($sp==int($sp)) ? sprintf("%d",$sp) : sprintf("%.1f",$sp);
  my $word = ($sp==1) ? "subpalette" : "subpalettes";
  my $ctastr = join(",", map {sprintf "\$%04X",$_} @ctas);
  # count colours changed from the clean original, to flag edited blocks
  my $modcol=0;
  { my $pp=$ba+1;
    for my $g (0..$c){
      my $mv=ord(substr($d,$pp,1)); my $mo=ord(substr($oa,$pp,1));
      for my $k (0..7){
        my $cv=ord(substr($d,$pp+1+$k,1))  | ((($mv>>(7-$k))&1)<<8);
        my $co=ord(substr($oa,$pp+1+$k,1)) | ((($mo>>(7-$k))&1)<<8);
        $modcol++ if $cv!=$co;
      }
      $pp+=9;
    }
  }
  my $modtag = $modcol ? sprintf("  *** MODIFIED: %d colour%s ***",$modcol,$modcol==1?"":"s") : "";
  # which level(s)/mode loaded this block (from the stage-tagged log)
  my @stg = sort {$a<=>$b} keys %{$blk{$ba}{stage} // {}};
  my @main = grep {$_<=7} @stg;
  my @used;
  if (@main==8) { push @used,"all levels"; }
  else { push @used, map {"L".($_+1)} @main; }
  push @used,"Special-1" if grep {$_==0x0A} @stg;   # $0A = select + 1st half
  push @used,"Special-2" if grep {$_==0x0B} @stg;   # $0B = score-gated 2nd half
  push @used, map {sprintf "stage\$%02X",$_} grep {$_>7 && $_!=0x0A && $_!=0x0B} @stg;
  my $usedtxt = @used ? join(",",@used) : "?";
  printf $O "; --- block \$%05X : CTA %s  %s  |  %d colours = %s %s  |  used: %s%s ---\n",
    $ba, $ctastr, join("  +  ",@loc), $colours, $sptxt, $word, $usedtxt, $modtag;
  printf $O "  .bank \$%02X\n    .org \$%04X\n", $bank,$org;
  printf $O "    .db \$%02X\n", $c;
  my $p=$ba+1;
  my @groups;
  for my $g (0..$c){
    my $mask=ord(substr($d,$p,1));
    my @col;
    for my $k (0..7){
      my $lo=ord(substr($d,$p+1+$k,1));
      push @col, $lo | ((($mask>>(7-$k))&1)<<8);
    }
    push @groups, [@col];
    # codec round-trip check
    my $m2=0; for my $k (0..7){ $m2=($m2<<1)|(($col[$k]>>8)&1); }
    $rtfail++ if $m2!=$mask;
    for my $k (0..7){ $rtfail++ if ($col[$k]&0xFF)!=ord(substr($d,$p+1+$k,1)); }
    $p+=9;
  }
  # emit groups in pairs (16 colours) with a #RRGGBB swatch comment above
  sub exp8 { int($_[0]*255/7 + 0.5) }   # 3-bit level -> 8-bit for preview
  for(my $gi=0; $gi<=$#groups; $gi+=2){
    my @pair = ($groups[$gi]);
    push @pair, $groups[$gi+1] if defined $groups[$gi+1];
    my @hex = map { sprintf "#%02x%02x%02x", exp8(($_>>3)&7), exp8(($_>>6)&7), exp8($_&7) } map {@$_} @pair;
    print $O "    ; ", join(" ",@hex), "\n";
    for my $grp (@pair){
      my @r = map { sprintf "rgb(%d,%d,%d)", ($_>>3)&7, ($_>>6)&7, $_&7 } @$grp;
      print $O "    pal8 ", join(", ",@r), "\n";
    }
  }
  print $O "\n";
}
close $O;

printf "wrote %s : %d blocks, %d total colours\n", $OUT, scalar(@abs),
       eval { my $t=0; $t+=($blk{$_}{count}+1)*8 for @abs; $t };
printf "overlaps: %d\n", scalar @ovl;
printf "  %s\n", join("  ", map {sprintf "\$%05X..\$%05X vs \$%05X",@$_} @ovl) if @ovl;
printf "codec round-trip failures: %d\n", $rtfail;
