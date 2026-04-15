const fs = require('fs');
const path = require('path');

const sourceFile = path.join(__dirname, 'node_modules', 'lucide', 'dist', 'umd', 'lucide.min.js');
const targetDir = path.join(__dirname, 'vendor');
const targetFile = path.join(targetDir, 'lucide.min.js');

if (!fs.existsSync(sourceFile)) {
    throw new Error(`Lucide bundle not found: ${sourceFile}`);
}

fs.mkdirSync(targetDir, { recursive: true });
fs.copyFileSync(sourceFile, targetFile);

console.log(`Copied Lucide bundle to ${targetFile}`);