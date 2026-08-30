#!/usr/bin/perl
# Generate palette-map.md : which palette blocks load in each level/section,
# from the stage-tagged capture log. Reference doc (colours live in palette.inc).
use strict; use warnings;

my $ROM  = "Parodius Da! - Shinwa kara Owarai he (J)_v4.pce";
my $ORIG = "Parodius_Da__original.pce";
my $LOG  = "parodius_pal_blocks.txt";
my $OUT  = "palette-map.md";

my $d;  { local $/; open my $F,"<:raw",$ROM  or die "$ROM: $!";  $d=<$F>;  }
my $oa; { local $/; open my $F,"<:raw",$ORIG or die "$ORIG: $!"; $oa=<$F>; }
sub byte { ord(substr($d,$_[0],1)) }

my (%blk,%stageblocks,%order,%seenstg);
open my $L,"<",$LOG or die "$LOG: $!";
while(<$L>){
  next unless /CTA=\$(\w+) block=\$\w+ block_abs=\$(\w+) count=\$(\w+).*stage=\$(\w+)/;
  my ($cta,$abs,$c,$s)=(hex($1),hex($2),hex($3),hex($4));
  $blk{$abs}{count}=$c; $blk{$abs}{cta}{$cta}=1; $blk{$abs}{stage}{$s}=1;
  $stageblocks{$s}{$abs}=1;
  unless($seenstg{$s}{$abs}){ $seenstg{$s}{$abs}=1; push @{$order{$s}}, $abs; }  # load order
}
close $L;

sub modcount {
  my $abs=shift; my $c=$blk{$abs}{count}; my ($m,$p)=(0,$abs+1);
  for my $g (0..$c){
    my $mv=byte($p); my $mo=ord(substr($oa,$p,1));
    for my $k (0..7){
      my $cv=byte($p+1+$k)        | ((($mv>>(7-$k))&1)<<8);
      my $co=ord(substr($oa,$p+1+$k,1)) | ((($mo>>(7-$k))&1)<<8);
      $m++ if $cv!=$co;
    }
    $p+=9;
  }
  return $m;
}
sub stage_name {
  my $s=shift;
  return "Level ".($s+1)." (also title / menu / intro / ending)" if $s==0;
  return "Level ".($s+1) if $s<=7;
  return "Special - part 1 (ship/power select + 1st half)" if $s==0x0A;
  return "Special - part 2 (score-gated 2nd half)" if $s==0x0B;
  return sprintf("stage \$%02X",$s);
}
sub loc {
  my $abs=shift; my %bysec;
  for my $cta (sort {$a<=>$b} keys %{$blk{$abs}{cta}}){
    my $sec=($cta>=0x100)?"sprite":"BG"; push @{$bysec{$sec}}, ($cta&0xFF)>>4;
  }
  my @o; for my $sec ("BG","sprite"){ push @o,"$sec ".join(",",@{$bysec{$sec}}) if $bysec{$sec} }
  return join(" + ",@o);
}
sub used_in {
  my @s=sort {$a<=>$b} keys %{$blk{$_[0]}{stage}};
  my @m=grep {$_<=7} @s; my @o;
  if(@m==8){ push @o,"all levels" } else { push @o, map {"L".($_+1)} @m }
  push @o,"Sp1" if grep{$_==0x0A}@s;
  push @o,"Sp2" if grep{$_==0x0B}@s;
  return join(", ",@o);
}
sub nstg { scalar keys %{$blk{$_[0]}{stage}} }
sub edited { my $m=modcount($_[0]); $m ? "yes ($m)" : "" }
sub banklog { sprintf("\$%02X:\$%04X", $_[0]>>13, 0x4000 + ($_[0] & 0x1FFF)) }  # = palette.inc .bank/.org
sub has_bg { for (keys %{$blk{$_[0]}{cta}}){ return 1 if $_<0x100 } return 0 }   # any BG CTA?
sub has_sp { for (keys %{$blk{$_[0]}{cta}}){ return 1 if $_>=0x100 } return 0 }  # any sprite CTA?
sub subs_sec { my($abs,$sp)=@_;                                                   # subpalette range(s) in one section
  my $span = int((($blk{$abs}{count}+1)*8 - 1)/16);   # extra subpalettes past the start (16 col each)
  my @x;
  for my $cta (sort {$a<=>$b} keys %{$blk{$abs}{cta}}){
    next unless ((($cta>=0x100)?1:0)==$sp);
    my $s=($cta&0xFF)>>4;
    push @x, $span ? "$s-".($s+$span) : "$s";
  }
  join(", ",@x) }

open my $O,">",$OUT or die;
print $O "# Parodius Da! - Palette Block Map\n\n";
print $O "Which colour-palette blocks load in each level / section, from a stage-tagged\n";
print $O "playthrough. Each block is a packed 9-bit palette; the editable colours live in\n";
print $O "[`palette.inc`](palette.inc). CTA = VCE index (0-255 = BG, 256-511 = sprite);\n";
print $O "1 subpalette = 16 colours. block (abs) = absolute ROM offset; bank:addr = the\n";
print $O ".bank / .org used in palette.inc (bank = abs>>13, org = \$4000 + (abs & \$1FFF)).\n";
print $O "\"edited (N)\" = N colours changed from the original.\n\n";
print $O "Each section splits its palettes into **Background** and **Sprite**, each listed\n";
print $O "**in the order it loaded** (from the capture log). `subpal` = the VCE subpalette(s)\n";
print $O "it fills (start-end; e.g. a 192-colour block at 0 fills 0-11). `used in` flags\n";
print $O "palettes shared with\n";
print $O "other sections. Blocks never seen loading (score-gated Special bosses, etc.) are\n";
print $O "in `palette.inc` as `used: ?`.\n\n";

# summary: block + edited-colour counts, split BG / sprite (BG carries most edits)
print $O "## Summary\n\n| section | BG blocks | BG edited cols | sprite blocks | sprite edited cols |\n|---|---|---|---|---|\n";
for my $s (sort {$a<=>$b} keys %stageblocks){
  my ($bgn,$bge,$spn,$spe)=(0,0,0,0);
  for my $abs (@{$order{$s}}){
    if(has_bg($abs)){ $bgn++; $bge+=modcount($abs) }
    if(has_sp($abs)){ $spn++; $spe+=modcount($abs) }
  }
  printf $O "| %s | %d | %d | %d | %d |\n", stage_name($s), $bgn, $bge, $spn, $spe;
}
# grand total over unique loaded blocks (each counted once, no double-count of shared)
my ($tbgn,$tbge,$tspn,$tspe)=(0,0,0,0);
for my $abs (keys %blk){
  next unless $blk{$abs}{stage};
  if(has_bg($abs)){ $tbgn++; $tbge+=modcount($abs) }
  if(has_sp($abs)){ $tspn++; $tspe+=modcount($abs) }
}
printf $O "| **All (unique blocks)** | **%d** | **%d** | **%d** | **%d** |\n", $tbgn,$tbge,$tspn,$tspe;
print $O "\n";

# per-stage: Background palettes then Sprite palettes, each in load order
for my $s (sort {$a<=>$b} keys %stageblocks){
  print $O "## ", stage_name($s), "  (stage `\$",sprintf("%02X",$s),"`)\n\n";
  for my $sp (0,1){
    my @list = grep { $sp ? has_sp($_) : has_bg($_) } @{$order{$s}};
    next unless @list;
    print $O ($sp ? "### Sprite palettes\n\n" : "### Background palettes\n\n");
    print $O "| # | block (abs) | bank:addr | subpal | colours | edited | used in |\n|---|---|---|---|---|---|---|\n";
    my $i=1;
    for my $abs (@list){
      printf $O "| %d | `\$%05X` | `%s` | %s | %d | %s | %s |\n",
        $i++, $abs, banklog($abs), subs_sec($abs,$sp), ($blk{$abs}{count}+1)*8, edited($abs), used_in($abs);
    }
    print $O "\n";
  }
}
close $O;

printf "wrote %s\n", $OUT;
