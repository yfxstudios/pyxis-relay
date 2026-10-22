// Draws the app icon (PyxisViewer/Assets.xcassets/AppIcon.appiconset/icon-1024.png).
// Run: swift make-icon.swift
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

let s = 1024
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
let ctx = CGContext(data: nil, width: s, height: s, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
// background: near-black vertical gradient
let bg = CGGradient(colorsSpace: cs, colors: [CGColor(srgbRed: 0.13, green: 0.14, blue: 0.16, alpha: 1),
                                               CGColor(srgbRed: 0.03, green: 0.03, blue: 0.04, alpha: 1)] as CFArray,
                    locations: [0, 1])!
ctx.drawLinearGradient(bg, start: CGPoint(x: 0, y: s), end: CGPoint(x: 0, y: 0), options: [])
let c = CGPoint(x: 512, y: 512)
// lens: outer ring, inner glass
ctx.setStrokeColor(CGColor(srgbRed: 0.92, green: 0.93, blue: 0.95, alpha: 1))
ctx.setLineWidth(46)
ctx.strokeEllipse(in: CGRect(x: c.x - 300, y: c.y - 300, width: 600, height: 600))
ctx.setLineWidth(14)
ctx.setStrokeColor(CGColor(srgbRed: 0.92, green: 0.93, blue: 0.95, alpha: 0.35))
ctx.strokeEllipse(in: CGRect(x: c.x - 215, y: c.y - 215, width: 430, height: 430))
let glass = CGGradient(colorsSpace: cs, colors: [CGColor(srgbRed: 0.22, green: 0.26, blue: 0.33, alpha: 1),
                                                  CGColor(srgbRed: 0.05, green: 0.06, blue: 0.08, alpha: 1)] as CFArray,
                       locations: [0, 1])!
ctx.saveGState()
ctx.addEllipse(in: CGRect(x: c.x - 200, y: c.y - 200, width: 400, height: 400))
ctx.clip()
ctx.drawRadialGradient(glass, startCenter: CGPoint(x: c.x - 70, y: c.y + 80), startRadius: 0,
                       endCenter: c, endRadius: 220, options: [])
ctx.restoreGState()
// live dot
ctx.setFillColor(CGColor(srgbRed: 0.94, green: 0.27, blue: 0.27, alpha: 1))
ctx.fillEllipse(in: CGRect(x: c.x - 70, y: c.y - 70, width: 140, height: 140))
let url = URL(fileURLWithPath: "PyxisViewer/Assets.xcassets/AppIcon.appiconset/icon-1024.png")
let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(dest, ctx.makeImage()!, nil)
CGImageDestinationFinalize(dest)
