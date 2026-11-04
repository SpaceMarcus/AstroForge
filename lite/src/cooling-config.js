/** Shared data-only contract for geometry-resolved regenerative cooling. */
export const CHANNEL_DEFAULTS = Object.freeze({
  mode:'channels',flowDirection:'counter',coolingStart:0,coolingEnd:1,channelCount:120,channelHeightMm:2,channelWidthFraction:0.65,
  wallThicknessMm:1,wallConductivityWmK:320,roughnessMm:0.005,minorK:1,
  wallLimitK:900,stations:120,throatCurvatureRatio:1.5,
});
export const CHANNEL_FIELDS = Object.freeze([
  {key:'channelCount',label:'Kanalanzahl',unit:'–',min:12,max:500,step:1},
  {key:'channelHeightMm',label:'Kanalhöhe',unit:'mm',min:0.2,max:10,step:0.1},
  {key:'channelWidthFraction',label:'Kanalbreite / lokale Teilung',unit:'–',min:0.1,max:0.9,step:0.01},
  {key:'wallThicknessMm',label:'Heißwanddicke',unit:'mm',min:0.2,max:5,step:0.1},
  {key:'wallConductivityWmK',label:'Wärmeleitfähigkeit der Wand',unit:'W/(m·K)',min:5,max:500,step:5},
  {key:'roughnessMm',label:'Kanalrauheit',unit:'mm',min:0,max:0.1,step:0.001},
  {key:'minorK',label:'Örtlicher Verlustbeiwert K',unit:'–',min:0,max:50,step:0.1},
  {key:'wallLimitK',label:'Vorgegebene Wandtemperaturgrenze',unit:'K',min:400,max:2000,step:10},
  {key:'stations',label:'Berechnungsstationen',unit:'–',min:40,max:400,step:1},
  {key:'throatCurvatureRatio',label:'Halskrümmungsradius / Halsradius',unit:'–',min:0.2,max:5,step:0.1},
]);
