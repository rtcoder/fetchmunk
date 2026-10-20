import AppKit
let output = URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
for (name,pixels) in [("icon_16x16.png",16),("icon_16x16@2x.png",32),("icon_32x32.png",32),("icon_32x32@2x.png",64),("icon_128x128.png",128),("icon_128x128@2x.png",256),("icon_256x256.png",256),("icon_256x256@2x.png",512),("icon_512x512.png",512),("icon_512x512@2x.png",1024)] {
    let size=CGFloat(pixels)
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:pixels,pixelsHigh:pixels,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap)
    NSColor(calibratedRed:0.91,green:0.39,blue:0.22,alpha:1).setFill()
    NSBezierPath(roundedRect:NSRect(x:size*0.08,y:size*0.08,width:size*0.84,height:size*0.84),xRadius:size*0.19,yRadius:size*0.19).fill()
    let arrow=NSBezierPath();arrow.lineWidth=size*0.065;arrow.lineCapStyle = .round;arrow.lineJoinStyle = .round
    arrow.move(to:NSPoint(x:size*0.5,y:size*0.74));arrow.line(to:NSPoint(x:size*0.5,y:size*0.38))
    arrow.move(to:NSPoint(x:size*0.34,y:size*0.53));arrow.line(to:NSPoint(x:size*0.5,y:size*0.37));arrow.line(to:NSPoint(x:size*0.66,y:size*0.53))
    NSColor.white.setStroke();arrow.stroke()
    let tray=NSBezierPath();tray.lineWidth=size*0.055;tray.lineCapStyle = .round
    tray.move(to:NSPoint(x:size*0.29,y:size*0.31));tray.line(to:NSPoint(x:size*0.29,y:size*0.25));tray.line(to:NSPoint(x:size*0.71,y:size*0.25));tray.line(to:NSPoint(x:size*0.71,y:size*0.31));tray.stroke()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent(name))
}
