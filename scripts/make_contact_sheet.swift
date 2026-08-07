import AppKit
import Foundation

guard CommandLine.arguments.count >= 3 else {
    fputs("usage: make_contact_sheet.swift OUTPUT INPUT...\n", stderr)
    exit(2)
}

let output = CommandLine.arguments[1]
let inputs = Array(CommandLine.arguments.dropFirst(2))
let columns = 5
let imageWidth: CGFloat = 352
let imageHeight: CGFloat = 240
let labelHeight: CGFloat = 28
let rows = Int(ceil(Double(inputs.count) / Double(columns)))
let canvas = NSImage(size: NSSize(width: imageWidth * CGFloat(columns),
                                  height: (imageHeight + labelHeight) * CGFloat(rows)))

canvas.lockFocus()
NSColor.black.setFill()
NSRect(origin: .zero, size: canvas.size).fill()

let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .medium),
    .foregroundColor: NSColor.white
]

for (index, path) in inputs.enumerated() {
    guard let image = NSImage(contentsOfFile: path) else { continue }
    let column = index % columns
    let row = index / columns
    let x = CGFloat(column) * imageWidth
    let y = canvas.size.height - CGFloat(row + 1) * (imageHeight + labelHeight)
    image.draw(in: NSRect(x: x, y: y + labelHeight, width: imageWidth, height: imageHeight))
    let label = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    label.draw(in: NSRect(x: x + 5, y: y + 6, width: imageWidth - 10, height: labelHeight - 8),
               withAttributes: attributes)
}

canvas.unlockFocus()
guard let tiff = canvas.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.88]) else {
    fputs("failed to render contact sheet\n", stderr)
    exit(1)
}
try jpeg.write(to: URL(fileURLWithPath: output))
